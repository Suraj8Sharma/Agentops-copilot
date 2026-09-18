import os

endpoint_code = """
@router.get(
    "/connections",
    summary="List user OAuth connections",
)
def get_connections(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    from app.db.supabase_client import create_client
    service_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    result = service_client.table("oauth_connections").select(
        "provider, status, scopes, expires_at, connected_at"
    ).eq("user_id", current_user.id).execute()
    return {"connections": result.data or []}

@router.delete(
    "/{provider}",
    summary="Disconnect OAuth provider",
)
def delete_connection(
    provider: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    from app.db.supabase_client import create_client
    service_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    service_client.table("oauth_connections").delete().eq("user_id", current_user.id).eq("provider", provider).execute()
    return {"message": "Disconnected"}
"""

with open('backend/app/api/routers/oauth.py', 'a', encoding='utf-8') as f:
    f.write(endpoint_code)
