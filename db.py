import os

from azure.cosmos import CosmosClient

# I store the credentials as environment variables, never hardcoded.
# Locally they come from a .env file that I gitignore.
# On Azure they are set as App Service application settings.
COSMOS_ENDPOINT = os.environ["COSMOS_ENDPOINT"]
COSMOS_KEY = os.environ["COSMOS_KEY"]
COSMOS_DATABASE = os.environ.get("COSMOS_DATABASE", "forge-db")

# I create one CosmosClient at startup and reuse it for every request.
# Creating a new connection on every request would be slow and wasteful.
_client = CosmosClient(COSMOS_ENDPOINT, COSMOS_KEY)
_database = _client.get_database_client(COSMOS_DATABASE)

# I have four containers, one for each entity.
# Each container's partition key is /id, meaning every document is
# looked up directly by its own ID. For a larger app I would partition
# messages by project_id for better query performance, but at this scale it's fine.
users_container = _database.get_container_client("users")
projects_container = _database.get_container_client("projects")
applications_container = _database.get_container_client("applications")
messages_container = _database.get_container_client("messages")
