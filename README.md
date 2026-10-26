# LAN Chat — File and Image Transfer Update

## Files
- `server.py`: TCP chat server, UDP discovery, private/group chat, chunked attachment relay.
- `gui_client.py`: Tkinter GUI with File and Image buttons.
- `database.py`: SQLite history, including attachment metadata and automatic migration of an older database.

## Setup
1. Back up your existing project folder.
2. Replace `server.py`, `gui_client.py`, and `database.py` with these files.
3. Run on the server laptop: `python server.py`
4. Run on each client laptop: `python gui_client.py`

No additional Python packages are required; this uses the Python standard library.

## Attachments
- Attachments can be sent in private chats and Group Chat.
- Images are transferred as image files and can be opened with the recipient's default image viewer.
- Received attachments are saved under `Received Files` beside `gui_client.py`.
- Maximum attachment size is 100 MB.
- The recipient must be online for private attachments. Group attachments go to users online at the time of sending.
- The server stores attachment metadata in SQLite, not the actual attachment bytes. A historical attachment can be opened only if the file still exists on that device.
- Use only on a trusted network. This simple LAN protocol does not encrypt chat text or attachment data.
