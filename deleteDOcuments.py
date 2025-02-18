from pymongo import MongoClient

# MongoDB connection details
MONGO_URI = "mongodb://localhost:27017/"
DATABASE_NAME = "seniorDesignTesting"
COLLECTION_NAME = "sendAndRecievePlantInfoTest"

def connect_to_mongodb():
    """Connects to MongoDB and returns a client."""
    client = MongoClient(MONGO_URI)
    client.admin.command("ping")  # Test connection
    print("Connected successfully to MongoDB")
    return client

def delete_all_documents():
    """Deletes all documents from the collection."""
    client = connect_to_mongodb()
    db = client[DATABASE_NAME]
    collection = db[COLLECTION_NAME]

    confirm = input("⚠️ Are you sure you want to delete ALL documents? (yes/no): ").strip().lower()
    if confirm != "yes":
        print(" Deletion aborted.")
        return

    result = collection.delete_many({})
    print(f" Deleted {result.deleted_count} documents from '{COLLECTION_NAME}'.")

    client.close()

if __name__ == "__main__":
    delete_all_documents()
