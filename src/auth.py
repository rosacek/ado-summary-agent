"""
Authentication helper using Azure CLI for tokens.
"""
import subprocess
import shutil

def get_access_token() -> str:
    """Obtain Azure DevOps access token via Azure CLI"""
    # Check if Azure CLI is installed
    if not shutil.which("az"):
        raise RuntimeError(
            "Azure CLI not found. Please install it from https://aka.ms/installazurecliwindows "
            "or provide ADO_PAT in your environment variables."
        )
    
    cmd = [
        "az",
        "account",
        "get-access-token",
        "--resource",
        "499b84ac-1321-427f-aa17-267ca6975798",  # Azure DevOps resource ID
        "--query",
        "accessToken",
        "-o",
        "tsv",
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        token = result.stdout.strip()
        if not token or result.returncode != 0:
            raise RuntimeError(
                f"Azure CLI token fetch failed. Please run 'az login' first. "
                f"Error: {result.stderr}"
            )
        return token
    except FileNotFoundError:
        raise RuntimeError(
            "Azure CLI not found. Please install it from https://aka.ms/installazurecliwindows "
            "or provide ADO_PAT in your environment variables."
        )
