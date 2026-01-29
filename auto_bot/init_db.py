from database.storage import storage

if __name__ == "__main__":
    print("Initializing Database...")
    storage.init_db()
    print("Done!")
