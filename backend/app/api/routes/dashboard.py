from fastapi import APIRouter, Depends, HTTPException
from app.models.user import TokenData
from app.api.deps import get_current_user
from app.db.mongodb import get_db
import pymongo
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
import io
import csv
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

router = APIRouter()

@router.get("/summary")
async def get_summary(current_user: TokenData = Depends(get_current_user)):
    db = get_db()
    
    pipeline = [
        {"$group": {
            "_id": "$qr_status",
            "count": {"$sum": 1}
        }}
    ]
    cursor = await db["events"].aggregate(pipeline)
    counts = {doc["_id"]: doc["count"] for doc in await cursor.to_list(length=100)}
    
    valid_qr = counts.get("VALID_QR", 0)
    no_qr = counts.get("NO_QR", 0)
    unreadable_qr = counts.get("UNREADABLE_QR", 0)
    invalid_qr = counts.get("INVALID_QR", 0)
    
    qr_exceptions = no_qr + unreadable_qr + invalid_qr
    overall_boxes = valid_qr + qr_exceptions
    
    success_count = await db["events"].count_documents({"status": "SUCCESS"})
    
    return {
        "overall_boxes": overall_boxes,
        "valid_qr": valid_qr,
        "no_qr": no_qr,
        "unreadable_qr": unreadable_qr,
        "invalid_qr": invalid_qr,
        "qr_exceptions": qr_exceptions,
        "inventory_added": success_count
    }

@router.get("/inventory")
async def get_inventory(current_user: TokenData = Depends(get_current_user)):
    db = get_db()
    
    pipeline = [
        {
            "$lookup": {
                "from": "products",
                "localField": "sku",
                "foreignField": "sku",
                "as": "product_info"
            }
        },
        {
            "$unwind": {
                "path": "$product_info",
                "preserveNullAndEmptyArrays": True
            }
        },
        {
            "$project": {
                "_id": 0,
                "sku": 1,
                "quantity": 1,
                "product_name": "$product_info.name",
                "is_active": "$product_info.is_active"
            }
        }
    ]
    cursor = await db["inventory"].aggregate(pipeline)
    inventory = await cursor.to_list(length=1000)
    return inventory

@router.get("/events")
async def get_events(limit: int = 50, current_user: TokenData = Depends(get_current_user)):
    db = get_db()
    
    events = await db["events"].find({}, {"_id": 0}).sort("timestamp", pymongo.DESCENDING).limit(limit).to_list(length=limit)
    return events

@router.get("/analytics")
async def get_analytics(range: str = "all", current_user: TokenData = Depends(get_current_user)):
    if range not in ["24h", "7d", "30d", "all"]:
        raise HTTPException(status_code=400, detail="Invalid range")

    now = datetime.utcnow()
    match_stage = None
    if range == "24h":
        start_time = now - timedelta(hours=24)
        date_format = "%Y-%m-%d %H:00"
        match_stage = {"$match": {"timestamp": {"$gte": start_time}}}
    elif range == "7d":
        start_time = now - timedelta(days=7)
        date_format = "%Y-%m-%d"
        match_stage = {"$match": {"timestamp": {"$gte": start_time}}}
    elif range == "30d":
        start_time = now - timedelta(days=30)
        date_format = "%Y-%m-%d"
        match_stage = {"$match": {"timestamp": {"$gte": start_time}}}
    else:
        date_format = "%Y-%m-%d"
        match_stage = {"$match": {"timestamp": {"$exists": True}}}
        
    db = get_db()
    
    # Trend pipeline
    trend_pipeline = [
        match_stage,
        {"$group": {
            "_id": {"$dateToString": {"format": date_format, "date": "$timestamp"}},
            "overall_boxes": {"$sum": 1},
            "valid_qr": {"$sum": {"$cond": [{"$eq": ["$qr_status", "VALID_QR"]}, 1, 0]}},
            "exceptions": {"$sum": {"$cond": [{"$in": ["$qr_status", ["NO_QR", "UNREADABLE_QR", "INVALID_QR"]]}, 1, 0]}}
        }},
        {"$sort": {"_id": 1}}
    ]
    trend_cursor = await db["events"].aggregate(trend_pipeline)
    trend_data = await trend_cursor.to_list(length=1000)
    
    formatted_trend = []
    for doc in trend_data:
        formatted_trend.append({
            "time": doc["_id"],
            "overall_boxes": doc["overall_boxes"],
            "valid_qr": doc["valid_qr"],
            "exceptions": doc["exceptions"]
        })

    # QR Status Distribution
    qr_pipeline = [
        match_stage,
        {"$group": {
            "_id": "$qr_status",
            "count": {"$sum": 1}
        }}
    ]
    qr_cursor = await db["events"].aggregate(qr_pipeline)
    qr_data = await qr_cursor.to_list(length=100)
    
    distribution = {doc["_id"]: doc["count"] for doc in qr_data}
    formatted_distribution = [
        {"name": "VALID_QR", "value": distribution.get("VALID_QR", 0)},
        {"name": "NO_QR", "value": distribution.get("NO_QR", 0)},
        {"name": "UNREADABLE_QR", "value": distribution.get("UNREADABLE_QR", 0)},
        {"name": "INVALID_QR", "value": distribution.get("INVALID_QR", 0)}
    ]
    # Filter out categories with 0 data
    formatted_distribution = [d for d in formatted_distribution if d["value"] > 0]
    
    return {
        "trend": formatted_trend,
        "distribution": formatted_distribution
    }

def build_report_query(start_date: Optional[str] = None, end_date: Optional[str] = None, qr_status: Optional[str] = None, sku: Optional[str] = None):
    query = {}
    if start_date or end_date:
        query["timestamp"] = {}
        if start_date:
            try:
                dt_start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
                query["timestamp"]["$gte"] = dt_start
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid start_date format")
        if end_date:
            try:
                if len(end_date) == 10:
                    dt_end = datetime.fromisoformat(end_date + "T23:59:59.999999")
                else:
                    dt_end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                query["timestamp"]["$lte"] = dt_end
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid end_date format")
    else:
        # Default bounded to last 7 days
        now = datetime.utcnow()
        query["timestamp"] = {"$gte": now - timedelta(days=7)}
        
    if qr_status and qr_status != "ALL":
        query["qr_status"] = qr_status
        
    if sku:
        query["sku"] = sku
        
    return query

@router.get("/reports")
async def get_reports(
    start_date: Optional[str] = None, 
    end_date: Optional[str] = None, 
    qr_status: Optional[str] = None, 
    sku: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user)
):
    db = get_db()
    query = build_report_query(start_date, end_date, qr_status, sku)
    
    # Get aggregates
    pipeline = [
        {"$match": query},
        {"$group": {
            "_id": "$qr_status",
            "count": {"$sum": 1},
            "success_count": {"$sum": {"$cond": [{"$eq": ["$status", "SUCCESS"]}, 1, 0]}}
        }}
    ]
    cursor = await db["events"].aggregate(pipeline)
    counts = await cursor.to_list(length=100)
    
    valid_qr = 0
    no_qr = 0
    unreadable_qr = 0
    invalid_qr = 0
    inventory_added = 0
    
    for doc in counts:
        status = doc["_id"]
        count = doc["count"]
        inventory_added += doc["success_count"]
        if status == "VALID_QR":
            valid_qr += count
        elif status == "NO_QR":
            no_qr += count
        elif status == "UNREADABLE_QR":
            unreadable_qr += count
        elif status == "INVALID_QR":
            invalid_qr += count
            
    qr_exceptions = no_qr + unreadable_qr + invalid_qr
    overall_boxes = valid_qr + qr_exceptions
    
    summary = {
        "overall_boxes": overall_boxes,
        "valid_qr": valid_qr,
        "no_qr": no_qr,
        "unreadable_qr": unreadable_qr,
        "invalid_qr": invalid_qr,
        "qr_exceptions": qr_exceptions,
        "inventory_added": inventory_added
    }
    
    # Get events
    events = await db["events"].find(query, {"_id": 0}).sort("timestamp", pymongo.DESCENDING).limit(500).to_list(length=500)
    
    return {
        "summary": summary,
        "events": events
    }

@router.get("/reports/export.csv")
async def export_reports_csv(
    start_date: Optional[str] = None, 
    end_date: Optional[str] = None, 
    qr_status: Optional[str] = None, 
    sku: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user)
):
    db = get_db()
    query = build_report_query(start_date, end_date, qr_status, sku)
    
    events = await db["events"].find(query, {"_id": 0}).sort("timestamp", pymongo.DESCENDING).limit(10000).to_list(length=10000)
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Timestamp", "Event ID", "Track ID", "QR Status", "QR Payload", "SKU", "Count Direction", "Inventory Status"])
    
    for e in events:
        writer.writerow([
            e.get("timestamp", ""),
            e.get("event_id", ""),
            e.get("track_id", ""),
            e.get("qr_status", ""),
            e.get("qr_payload", "") or "-",
            e.get("sku", "") or "-",
            e.get("count_direction", ""),
            e.get("status", "")
        ])
        
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=inventory-report-{datetime.utcnow().strftime('%Y-%m-%d')}.csv"}
    )


@router.get("/reports/export.pdf")
async def export_reports_pdf(
    start_date: Optional[str] = None, 
    end_date: Optional[str] = None, 
    qr_status: Optional[str] = None, 
    sku: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user)
):
    db = get_db()
    query = build_report_query(start_date, end_date, qr_status, sku)
    
    # Get aggregates
    pipeline = [
        {"$match": query},
        {"$group": {
            "_id": "$qr_status",
            "count": {"$sum": 1},
            "success_count": {"$sum": {"$cond": [{"$eq": ["$status", "SUCCESS"]}, 1, 0]}}
        }}
    ]
    cursor = await db["events"].aggregate(pipeline)
    counts = await cursor.to_list(length=100)
    
    valid_qr = 0
    no_qr = 0
    unreadable_qr = 0
    invalid_qr = 0
    inventory_added = 0
    
    for doc in counts:
        status = doc["_id"]
        count = doc["count"]
        inventory_added += doc["success_count"]
        if status == "VALID_QR":
            valid_qr += count
        elif status == "NO_QR":
            no_qr += count
        elif status == "UNREADABLE_QR":
            unreadable_qr += count
        elif status == "INVALID_QR":
            invalid_qr += count
            
    qr_exceptions = no_qr + unreadable_qr + invalid_qr
    overall_boxes = valid_qr + qr_exceptions
    
    events = await db["events"].find(query, {"_id": 0}).sort("timestamp", pymongo.DESCENDING).limit(10000).to_list(length=10000)
    
    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=landscape(letter), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=18)
    styles = getSampleStyleSheet()
    elements = []
    
    elements.append(Paragraph("SMART INVENTORY MANAGEMENT", styles['Title']))
    elements.append(Paragraph("Inventory Processing Report", styles['Heading2']))
    elements.append(Spacer(1, 12))
    
    # Info
    date_range_str = f"{start_date or 'All'} to {end_date or 'All'}"
    elements.append(Paragraph(f"<b>Generated:</b> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC", styles['Normal']))
    elements.append(Paragraph(f"<b>Date Range:</b> {date_range_str}", styles['Normal']))
    elements.append(Paragraph(f"<b>QR Status Filter:</b> {qr_status or 'All'}", styles['Normal']))
    elements.append(Paragraph(f"<b>SKU Filter:</b> {sku or 'All'}", styles['Normal']))
    elements.append(Spacer(1, 12))
    
    # Summary
    elements.append(Paragraph("<b>Summary</b>", styles['Heading3']))
    summary_data = [
        ["Overall Boxes", "Valid QR", "QR Exceptions", "Inventory Added"],
        [str(overall_boxes), str(valid_qr), str(qr_exceptions), str(inventory_added)]
    ]
    t = Table(summary_data, colWidths=[120, 120, 120, 120])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.black),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 6),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 12))
    
    # QR Status Breakdown
    elements.append(Paragraph("<b>QR Status Breakdown</b>", styles['Heading3']))
    breakdown_data = [["Status", "Count"]]
    if valid_qr > 0 or qr_status in ["VALID_QR", "ALL", None]: breakdown_data.append(["VALID_QR", str(valid_qr)])
    if no_qr > 0 or qr_status in ["NO_QR", "ALL", None]: breakdown_data.append(["NO_QR", str(no_qr)])
    if unreadable_qr > 0 or qr_status in ["UNREADABLE_QR", "ALL", None]: breakdown_data.append(["UNREADABLE_QR", str(unreadable_qr)])
    if invalid_qr > 0 or qr_status in ["INVALID_QR", "ALL", None]: breakdown_data.append(["INVALID_QR", str(invalid_qr)])
    
    t2 = Table(breakdown_data, colWidths=[150, 100])
    t2.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
    ]))
    elements.append(t2)
    elements.append(Spacer(1, 24))
    
    # Detailed Events
    limit_text = " (Maximum export limit: 10,000 events.)" if len(events) == 10000 else ""
    elements.append(Paragraph(f"<b>Detailed Events{limit_text}</b>", styles['Heading3']))
    
    table_data = [["Timestamp", "Event ID", "Track ID", "QR Status", "QR Payload", "SKU", "Direction", "Inventory"]]
    
    # We will use a smaller font for the events table
    for e in events:
        table_data.append([
            str(e.get("timestamp", "")),
            str(e.get("event_id", ""))[:8] + "...", # Truncate event ID for space
            str(e.get("track_id", "")),
            str(e.get("qr_status", "")),
            str(e.get("qr_payload", "") or "-"),
            str(e.get("sku", "") or "-"),
            str(e.get("count_direction", "")),
            str(e.get("status", ""))
        ])
        
    t3 = Table(table_data, colWidths=[110, 60, 50, 80, 100, 80, 60, 70], repeatRows=1)
    t3.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#2c3e50")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,0), 6),
        ('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.whitesmoke])
    ]))
    elements.append(t3)
    
    doc.build(elements)
    
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=inventory-report-{datetime.utcnow().strftime('%Y-%m-%d')}.pdf"}
    )

