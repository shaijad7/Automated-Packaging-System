from config import settings
from pymongo import MongoClient

print("MONGODB_URI used:", "mongodb+srv://" in settings.MONGODB_URI)

client = MongoClient(settings.MONGODB_URI)
db = client.get_database("smart_inventory")
product = db["products"].find_one({"sku": "ADP-001"})
print("Query Result for ADP-001:", product)
