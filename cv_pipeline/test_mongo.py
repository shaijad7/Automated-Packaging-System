import os
from pymongo import MongoClient
import certifi

uri = os.getenv("MONGODB_URI")
if not uri:
    print("MONGODB_URI not set. CV pipeline communicates exclusively via HTTP API, not direct MongoDB.")
else:
    test_db = os.getenv("MONGODB_DB_NAME", "smart_inventory_test_cv")
    if "test" not in test_db.lower() or test_db.lower() == "smart_inventory":
        raise ValueError(f"Unsafe database target rejected: {test_db}")
    client = MongoClient(uri, tlsCAFile=certifi.where())
    db = client.get_database(test_db)
    product = db["products"].find_one({"sku": "ADP-001"})
    print("Query Result for ADP-001 in test db:", product)
