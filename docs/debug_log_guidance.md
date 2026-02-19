# Debug log collection and uploads

Debug logging already writes per-round text files so you can attach full traces to reports without converting them to images.

1. **Enable logging:** In the admin "Group Game Supervision" panel, toggle **Enable debug logging** before starting or resuming a game. The backend will persist a UTF-8 `.txt` file for every round.
2. **Locate the files:** Logs are saved under `backend/debug_logs_root/` with the game id and name in the filename. You can copy or download them directly from the server or container file system.
3. **Share as text:** Because the UI restricts image uploads for avatars/logos, attach the `.txt` files through your issue tracker or file storage instead of the profile/logo upload controls. No format conversion is needed—the files are plain text.
4. **Troubleshooting:** If a log is missing, verify the debug toggle was on, that the backend user can write to `backend/debug_logs_root/`, and that the game completed at least one round.

These steps avoid the image-only upload widgets and keep the original text logs intact for debugging.
