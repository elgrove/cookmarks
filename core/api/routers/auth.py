from django.contrib.auth import authenticate, login, logout
from ninja import Router

from core.api.auth import get_or_create_admin, no_auth_enabled
from core.api.schemas import LoginIn, MessageOut, UserOut

router = Router()


def _user_to_out(user) -> dict:
    return {"id": user.id, "username": user.username, "is_staff": user.is_staff}


@router.post("/login", auth=None, response={200: UserOut, 401: MessageOut})
def login_view(request, data: LoginIn):
    if no_auth_enabled():
        user = get_or_create_admin()
        login(request, user)
        return 200, _user_to_out(user)

    user = authenticate(request, username=data.username, password=data.password)
    if not user:
        return 401, {"detail": "Invalid credentials"}
    login(request, user)
    return 200, _user_to_out(user)


@router.post("/logout", auth=None, response={200: MessageOut})
def logout_view(request):
    logout(request)
    return 200, {"detail": "Logged out"}


@router.get("/me", auth=None, response={200: UserOut, 401: MessageOut})
def me_view(request):
    if no_auth_enabled():
        user = get_or_create_admin()
        return 200, _user_to_out(user)
    if request.user.is_authenticated:
        return 200, _user_to_out(request.user)
    return 401, {"detail": "Not authenticated"}


@router.get("/config", auth=None, response={200: dict})
def auth_config(request):
    return 200, {"no_auth": no_auth_enabled()}
