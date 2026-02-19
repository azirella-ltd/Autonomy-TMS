from app.core.config import Settings

class TempSettings(Settings):
    SQLALCHEMY_DATABASE_URI: str = "mysql+pymysql://root:19890617@localhost/autonomy"

temp_settings = TempSettings()
