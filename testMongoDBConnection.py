from pymongo import MongoClient

MONGO_URI = "mongodb://localhost:27017/"
DATABASE_NAME = "seniorDesignTesting"
COLLECTION_NAME = "sendAndRecievePlantInfoTest"

try:
    client = MongoClient(MONGO_URI)
    client.admin.command("ping")
    print("Connected successfully")

    db = client[DATABASE_NAME]
    collection = db[COLLECTION_NAME]

    # Insert a test document
    doc = {"test_key": "test_value"}
    result = collection.insert_one(doc)
    print("Inserted doc with ID:", result.inserted_id)

    # Find and print the document to verify it was inserted
    inserted_doc = collection.find_one({"_id": result.inserted_id})
    print("Fetched document:", inserted_doc)

    client.close()

except Exception as e:
    print("The following error occurred:", e)
