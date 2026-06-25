import os

from azure.cosmos import CosmosClient

COSMOS_ENDPOINT = os.environ["COSMOS_ENDPOINT"]
COSMOS_KEY = os.environ["COSMOS_KEY"]
COSMOS_DATABASE = os.environ.get("COSMOS_DATABASE", "forge-db")

_client = CosmosClient(COSMOS_ENDPOINT, COSMOS_KEY)
_database = _client.get_database_client(COSMOS_DATABASE)

users_container = _database.get_container_client("users")
projects_container = _database.get_container_client("projects")
applications_container = _database.get_container_client("applications")
messages_container = _database.get_container_client("messages")
