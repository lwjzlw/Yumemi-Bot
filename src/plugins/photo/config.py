from pydantic import BaseModel
from src.utils.paths import CHARACTER_DATA_PATH, IMAGE_RESOURCE_DIR


class PluginConfig(BaseModel):
    image_base_folder: str = str(IMAGE_RESOURCE_DIR)
    character_json_path: str = str(CHARACTER_DATA_PATH)
    photo_superusers: list[str] = []
    photo_restricted_mode: bool = False
    photo_allowed_users: list[str] = []
    photo_allowed_groups: list[str] = []
    photo_unlimited_users: list[str] = []
    photo_rate_limited_users: list[str] = []
    photo_disabled_users: list[str] = []
    photo_unlimited_groups: list[str] = []
    photo_rate_limited_groups: list[str] = []
    photo_disabled_groups: list[str] = []
    photo_rate_limit: int = 3
    photo_single_request_limit: int = 3
    photo_max_count: int = 9
