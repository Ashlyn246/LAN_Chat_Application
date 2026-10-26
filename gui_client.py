
import socket
import threading
import json
import tkinter as tk
from tkinter import simpledialog, messagebox, filedialog
from datetime import datetime
from pathlib import Path
import os
import base64
import uuid
import shutil

PORT = 5000
DISCOVERY_PORT = 5001
CHUNK_SIZE = 48 * 1024
MAX_FILE_SIZE = 100 * 1024 * 1024

BG = "#171923"
PANEL = "#202434"
CARD = "#292F40"
ACCENT = "#8B5CF6"
TEXT = "#F3F4F6"
MUTED = "#9CA3AF"
GREEN = "#4ADE80"

BASE_DIR = Path(__file__).resolve().parent
ATTACHMENTS_DIR = BASE_DIR / "Attachments"
SENT_DIR = ATTACHMENTS_DIR / "Sent"
RECEIVED_DIR = ATTACHMENTS_DIR / "Received"

ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
SENT_DIR.mkdir(parents=True, exist_ok=True)
RECEIVED_DIR.mkdir(parents=True, exist_ok=True)


def find_server():
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    udp.settimeout(5)

    try:
        udp.sendto(
            b"LAN_CHAT_DISCOVER",
            ("255.255.255.255", DISCOVERY_PORT)
        )
        data, _ = udp.recvfrom(1024)
        return json.loads(data.decode())["server_ip"]

    except (OSError, ValueError, KeyError):
        return None

    finally:
        udp.close()


def get_attachment_path(transfer_id, file_name):
    """Find a locally saved sent or received attachment."""

    if not file_name:
        return None

    safe_name = Path(file_name).name

    if transfer_id:
        archived_name = f"{transfer_id}__{safe_name}"

        candidates = [
            SENT_DIR / archived_name,
            RECEIVED_DIR / archived_name,
        ]

        for candidate in candidates:
            if candidate.is_file():
                return str(candidate.resolve())

    # Backward compatibility with files saved by older versions.
    old_received = BASE_DIR / "Received Files" / safe_name

    if old_received.is_file():
        return str(old_received.resolve())

    return None


root = tk.Tk()
root.withdraw()
root.title("LAN Chat")
root.geometry("1000x680")
root.minsize(750, 500)
root.configure(bg=BG)

name = simpledialog.askstring(
    "LAN Chat",
    "Enter your display name:",
    parent=root
)

if not name or not name.strip():
    root.destroy()
    raise SystemExit

name = name.strip()

server_ip = find_server()

if not server_ip:
    messagebox.showerror("Connection Error", "Server not found.")
    root.destroy()
    raise SystemExit

try:
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect((server_ip, PORT))
    client_file = client.makefile("r", encoding="utf-8")

    client.sendall(
        (json.dumps({"name": name}) + "\n").encode("utf-8")
    )

except OSError as error:
    messagebox.showerror("Connection Error", str(error))
    root.destroy()
    raise SystemExit


root.deiconify()

contacts = []
online_users = []
current_chat = "Group Chat"

conversations = {"Group Chat": []}

send_lock = threading.Lock()

# transfer_id -> active receiving transfer information
active_receives = {}

# transfer_id -> locally saved file path
local_paths = {}


def format_size(size):
    size = int(size or 0)

    if size < 1024:
        return f"{size} B"

    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"

    return f"{size / (1024 * 1024):.1f} MB"


main = tk.Frame(root, bg=BG)
main.pack(fill="both", expand=True)

sidebar = tk.Frame(main, bg=PANEL, width=260)
sidebar.pack(side="left", fill="y")
sidebar.pack_propagate(False)

tk.Label(
    sidebar,
    text="LAN CHAT",
    bg=PANEL,
    fg=TEXT,
    font=("Segoe UI", 17, "bold")
).pack(anchor="w", padx=18, pady=(20, 4))

tk.Label(
    sidebar,
    text=name,
    bg=PANEL,
    fg=GREEN,
    font=("Segoe UI", 10)
).pack(anchor="w", padx=18, pady=(0, 18))

tk.Label(
    sidebar,
    text="CONVERSATIONS",
    bg=PANEL,
    fg=MUTED,
    font=("Segoe UI", 9, "bold")
).pack(anchor="w", padx=18, pady=(0, 8))

contact_frame = tk.Frame(sidebar, bg=PANEL)
contact_frame.pack(fill="both", expand=True, padx=8)

content = tk.Frame(main, bg=BG)
content.pack(side="left", fill="both", expand=True)

header = tk.Frame(content, bg=PANEL, height=65)
header.pack(fill="x")
header.pack_propagate(False)

chat_title = tk.Label(
    header,
    text="Group Chat",
    bg=PANEL,
    fg=TEXT,
    font=("Segoe UI", 14, "bold")
)
chat_title.pack(side="left", padx=20, pady=15)

chat_status = tk.Label(
    header,
    text="Everyone",
    bg=PANEL,
    fg=MUTED,
    font=("Segoe UI", 9)
)
chat_status.pack(side="right", padx=20)

messages_canvas = tk.Canvas(
    content,
    bg=BG,
    highlightthickness=0
)

scrollbar = tk.Scrollbar(
    content,
    orient="vertical",
    command=messages_canvas.yview
)

messages_canvas.configure(yscrollcommand=scrollbar.set)

scrollbar.pack(side="right", fill="y")
messages_canvas.pack(fill="both", expand=True)

messages_frame = tk.Frame(messages_canvas, bg=BG)

canvas_window = messages_canvas.create_window(
    (0, 0),
    window=messages_frame,
    anchor="nw"
)


def resize_messages(event=None):
    messages_canvas.configure(
        scrollregion=messages_canvas.bbox("all")
    )

    messages_canvas.itemconfigure(
        canvas_window,
        width=messages_canvas.winfo_width()
    )


messages_frame.bind("<Configure>", resize_messages)
messages_canvas.bind("<Configure>", resize_messages)

bottom = tk.Frame(content, bg=PANEL)
bottom.pack(fill="x", side="bottom")

entry = tk.Entry(
    bottom,
    bg=CARD,
    fg=TEXT,
    insertbackground=TEXT,
    relief="flat",
    font=("Segoe UI", 11)
)

entry.pack(
    side="left",
    fill="x",
    expand=True,
    padx=(14, 8),
    pady=14,
    ipady=10
)

file_button = tk.Button(
    bottom,
    text="File",
    bg=CARD,
    fg=TEXT,
    activebackground=CARD,
    relief="flat",
    font=("Segoe UI", 10, "bold"),
    padx=12,
    pady=8
)

file_button.pack(side="left", padx=(0, 6), pady=14)

image_button = tk.Button(
    bottom,
    text="Image",
    bg=CARD,
    fg=TEXT,
    activebackground=CARD,
    relief="flat",
    font=("Segoe UI", 10, "bold"),
    padx=12,
    pady=8
)

image_button.pack(side="left", padx=(0, 6), pady=14)

send_button = tk.Button(
    bottom,
    text="Send",
    bg=ACCENT,
    fg="white",
    activebackground=ACCENT,
    relief="flat",
    font=("Segoe UI", 10, "bold"),
    padx=20,
    pady=8
)

send_button.pack(side="right", padx=(0, 14), pady=14)


def send_packet(packet):
    try:
        payload = (
            json.dumps(packet, ensure_ascii=False) + "\n"
        ).encode("utf-8")

        with send_lock:
            client.sendall(payload)

        return True

    except OSError:
        root.after(
            0,
            lambda: messagebox.showerror(
                "Connection Error",
                "Connection to server lost."
            )
        )
        return False


def open_attachment(path):
    """Open a locally saved attachment."""

    try:
        if not path:
            messagebox.showinfo(
                "Attachment",
                "No local copy of this attachment exists on this device."
            )
            return

        path = Path(path)

        if path.is_file():
            os.startfile(str(path.resolve()))
        else:
            messagebox.showinfo(
                "Attachment",
                "The local file could not be found. "
                "It may have been moved or deleted."
            )

    except (OSError, AttributeError) as error:
        messagebox.showerror("Attachment", str(error))


def resolve_attachment_path(item):
    """Resolve the file path when displaying an attachment."""

    transfer_id = item.get("transfer_id")
    file_name = item.get("file_name")

    path = item.get("local_path")

    if path and Path(path).is_file():
        return str(Path(path).resolve())

    path = local_paths.get(transfer_id)

    if path and Path(path).is_file():
        return str(Path(path).resolve())

    path = get_attachment_path(transfer_id, file_name)

    if path:
        item["local_path"] = path

    return path


def add_bubble(item):
    sender = item.get("sender", "")
    timestamp = item.get("timestamp", "")
    outgoing = sender == name
    kind = item.get("kind", "text")

    row = tk.Frame(messages_frame, bg=BG)
    row.pack(fill="x", padx=12, pady=5)

    bubble_bg = "#4C3586" if outgoing else CARD
    side = "right" if outgoing else "left"

    bubble = tk.Frame(
        row,
        bg=bubble_bg,
        padx=12,
        pady=8
    )

    bubble.pack(
        side=side,
        anchor="e" if outgoing else "w"
    )

    tk.Label(
        bubble,
        text=sender,
        bg=bubble_bg,
        fg=GREEN if not outgoing else "#DDD6FE",
        font=("Segoe UI", 9, "bold")
    ).pack(anchor="w")

    if kind in ("file", "image"):
        filename = (
            item.get("file_name")
            or item.get("message", "Attachment")
        )

        label = "Image" if kind == "image" else "File"
        size_text = format_size(item.get("file_size", 0))

        tk.Label(
            bubble,
            text=f"{'🖼' if kind == 'image' else '📎'} {filename}",
            bg=bubble_bg,
            fg=TEXT,
            font=("Segoe UI", 10, "bold"),
            wraplength=420,
            justify="left"
        ).pack(anchor="w", pady=(4, 2))

        tk.Label(
            bubble,
            text=f"{label} • {size_text}",
            bg=bubble_bg,
            fg="#C4C4D0",
            font=("Segoe UI", 8)
        ).pack(anchor="w", pady=(0, 4))

        path = resolve_attachment_path(item)

        if item.get("complete") is False:
            tk.Label(
                bubble,
                text="Receiving...",
                bg=bubble_bg,
                fg=MUTED,
                font=("Segoe UI", 8)
            ).pack(anchor="w")

        # Always display Open. Resolve the path again when clicked.
        tk.Button(
            bubble,
            text="Open",
            command=lambda current_item=item: open_attachment(
                resolve_attachment_path(current_item)
            ),
            bg=ACCENT,
            fg="white",
            activebackground=ACCENT,
            relief="flat",
            padx=10
        ).pack(anchor="w", pady=(4, 0))

    else:
        tk.Label(
            bubble,
            text=item.get("message", ""),
            bg=bubble_bg,
            fg=TEXT,
            font=("Segoe UI", 10),
            wraplength=420,
            justify="left"
        ).pack(anchor="w", pady=(3, 4))

    tk.Label(
        bubble,
        text=timestamp,
        bg=bubble_bg,
        fg="#C4C4D0",
        font=("Segoe UI", 8)
    ).pack(anchor="e", pady=(4, 0))

    messages_canvas.update_idletasks()
    messages_canvas.yview_moveto(1)


def show_conversation():
    for widget in messages_frame.winfo_children():
        widget.destroy()

    chat_title.config(text=current_chat)

    if current_chat == "Group Chat":
        chat_status.config(
            text="Group conversation",
            fg=MUTED
        )
    elif current_chat in online_users:
        chat_status.config(text="● Online", fg=GREEN)
    else:
        chat_status.config(text="● Offline", fg=MUTED)

    for item in conversations.get(current_chat, []):
        add_bubble(item)


def choose_chat(chat):
    global current_chat

    current_chat = chat
    conversations.setdefault(chat, [])

    show_conversation()

    if chat == "Group Chat":
        send_packet({"type": "get_group_history"})
    else:
        send_packet({
            "type": "get_private_history",
            "contact": chat
        })


def refresh_contacts():
    for widget in contact_frame.winfo_children():
        widget.destroy()

    all_contacts = ["Group Chat"] + [
        contact for contact in contacts if contact != name
    ]

    for contact in all_contacts:
        is_online = (
            contact == "Group Chat"
            or contact in online_users
        )

        symbol = "●" if is_online else "○"
        color = GREEN if is_online else MUTED

        tk.Button(
            contact_frame,
            text=f"{symbol}  {contact}",
            anchor="w",
            bg=CARD if contact == current_chat else PANEL,
            fg=color if contact != current_chat else TEXT,
            activebackground=CARD,
            activeforeground=TEXT,
            relief="flat",
            padx=12,
            pady=11,
            font=("Segoe UI", 10),
            command=lambda c=contact: choose_chat(c)
        ).pack(fill="x", pady=2)


def add_or_update_attachment(data):
    chat_type = data.get(
        "chat_type",
        "group" if data.get("type") == "group" else "private"
    )

    sender = data.get("sender", "")

    chat = (
        "Group Chat"
        if chat_type == "group"
        else (
            data.get("recipient")
            if sender == name
            else sender
        )
    )

    conversations.setdefault(chat, [])

    message_id = data.get("message_id")
    transfer_id = data.get("transfer_id")

    existing = next(
        (
            item for item in conversations[chat]
            if item.get("id") == message_id
            and message_id is not None
        ),
        None
    )

    if existing is None:
        existing = {
            "id": message_id,
            "sender": sender,
            "message": f"[Attachment] {data.get('file_name', '')}",
            "timestamp": data.get(
                "timestamp",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ),
            "kind": data.get("kind", "file"),
            "file_name": data.get("file_name", "attachment"),
            "file_size": data.get("file_size", 0),
            "transfer_id": transfer_id,
            "complete": False
        }

        conversations[chat].append(existing)

    else:
        # Keep metadata up to date if the server sends it again.
        existing["transfer_id"] = transfer_id or existing.get("transfer_id")
        existing["file_name"] = data.get(
            "file_name",
            existing.get("file_name", "attachment")
        )
        existing["file_size"] = data.get(
            "file_size",
            existing.get("file_size", 0)
        )
        existing["kind"] = data.get(
            "kind",
            existing.get("kind", "file")
        )

    # Only the receiving client writes incoming chunks to disk.
    if sender != name and data.get("type") == "attachment_start":
        safe_name = Path(existing["file_name"]).name

        destination = RECEIVED_DIR / (
            f"{transfer_id}__{safe_name}"
        )

        try:
            if transfer_id in active_receives:
                if chat == current_chat:
                    show_conversation()
                return

            file_handle = open(destination, "wb")

            active_receives[transfer_id] = {
                "file": file_handle,
                "path": str(destination.resolve()),
                "received": 0,
                "expected": int(existing.get("file_size", 0)),
                "chat": chat,
                "item": existing
            }

            existing["local_path"] = str(destination.resolve())
            local_paths[transfer_id] = str(destination.resolve())

        except OSError as error:
            messagebox.showerror(
                "Receive attachment",
                str(error)
            )

    if chat == current_chat:
        show_conversation()


def history_item(item):
    """Convert a database history record into a display item."""

    transfer_id = item.get("transfer_id")
    file_name = item.get("file_name")

    local_path = None

    if file_name:
        local_path = get_attachment_path(
            transfer_id,
            file_name
        )

    result = {
        "id": item.get("id"),
        "sender": item.get("sender", ""),
        "message": item.get("message", ""),
        "timestamp": item.get("timestamp", ""),
        "kind": item.get("kind", "text"),
        "file_name": file_name,
        "file_size": item.get("file_size", 0),
        "transfer_id": transfer_id,
        "local_path": local_path,
        "complete": True
    }

    if local_path and transfer_id:
        local_paths[transfer_id] = local_path

    return result


def process_message(data):
    global contacts, online_users

    kind = data.get("type")

    if kind == "error":
        messagebox.showerror(
            "LAN Chat",
            data.get("message", "Error")
        )
        return

    if kind == "attachment_error":
        messagebox.showerror(
            "Attachment transfer",
            data.get("message", "Transfer failed.")
        )
        return

    if kind == "contacts":
        contacts = data.get("contacts", [])
        online_users = data.get("online", [])

        refresh_contacts()
        show_conversation()
        return

    if kind == "private_history":
        contact = data.get("contact", "")

        conversations[contact] = [
            history_item(item)
            for item in data.get("messages", [])
        ]

        if current_chat == contact:
            show_conversation()

        return

    if kind == "group_history":
        conversations["Group Chat"] = [
            history_item(item)
            for item in data.get("messages", [])
        ]

        if current_chat == "Group Chat":
            show_conversation()

        return

    if kind in ("private", "group"):
        chat = (
            "Group Chat"
            if kind == "group"
            else (
                data.get("recipient")
                if data.get("sender") == name
                else data.get("sender")
            )
        )

        conversations.setdefault(chat, [])
        message_id = data.get("message_id")

        if not any(
            item.get("id") == message_id
            for item in conversations[chat]
        ):
            conversations[chat].append({
                "id": message_id,
                "sender": data.get("sender", ""),
                "message": data.get("message", ""),
                "timestamp": data.get(
                    "timestamp",
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ),
                "kind": "text"
            })

        if kind == "private" and message_id:
            send_packet({
                "type": "ack",
                "message_id": message_id
            })

        if chat == current_chat:
            show_conversation()

        return

    if kind == "attachment_start":
        add_or_update_attachment(data)
        return

    if kind == "attachment_chunk":
        transfer_id = data.get("transfer_id")
        transfer = active_receives.get(transfer_id)

        if transfer:
            try:
                chunk = base64.b64decode(
                    data.get("data", ""),
                    validate=True
                )

                transfer["file"].write(chunk)
                transfer["received"] += len(chunk)

            except (OSError, ValueError) as error:
                try:
                    transfer["file"].close()
                except OSError:
                    pass

                active_receives.pop(transfer_id, None)

                messagebox.showerror(
                    "Attachment transfer",
                    f"Could not save the incoming attachment: {error}"
                )

        return

    if kind == "attachment_end":
        transfer_id = data.get("transfer_id")
        transfer = active_receives.pop(transfer_id, None)

        if transfer:
            try:
                transfer["file"].close()

                transfer["item"]["complete"] = True
                transfer["item"]["local_path"] = transfer["path"]

                local_paths[transfer_id] = transfer["path"]

            except OSError as error:
                messagebox.showerror(
                    "Attachment transfer",
                    str(error)
                )

            if transfer["chat"] == current_chat:
                show_conversation()

        # Mark the sender's matching conversation item as complete.
        for chat_items in conversations.values():
            for item in chat_items:
                if item.get("transfer_id") == transfer_id:
                    item["complete"] = True

        if current_chat in conversations:
            show_conversation()


def receive_messages():
    try:
        for line in client_file:
            if not line:
                break

            try:
                data = json.loads(line)
                root.after(0, process_message, data)

            except json.JSONDecodeError:
                continue

    except (OSError, ValueError):
        pass


def send_current_message(event=None):
    text = entry.get().strip()

    if not text:
        return

    packet = (
        {"type": "group", "message": text}
        if current_chat == "Group Chat"
        else {
            "type": "private",
            "recipient": current_chat,
            "message": text
        }
    )

    if send_packet(packet):
        entry.delete(0, "end")


def send_attachment(path, attachment_kind):
    path = Path(path)

    if not path.is_file():
        return

    try:
        size = path.stat().st_size

    except OSError as error:
        messagebox.showerror("Attachment", str(error))
        return

    if size > MAX_FILE_SIZE:
        messagebox.showerror(
            "Attachment",
            "Maximum attachment size is 100 MB."
        )
        return

    if current_chat != "Group Chat" and current_chat not in online_users:
        messagebox.showwarning(
            "Contact offline",
            "The recipient must be online to receive an attachment."
        )
        return

    chat_snapshot = current_chat
    transfer_id = str(uuid.uuid4())

    recipient = (
        ""
        if chat_snapshot == "Group Chat"
        else chat_snapshot
    )

    chat_type = (
        "group"
        if chat_snapshot == "Group Chat"
        else "private"
    )

    def worker():
        # Archive the source file so the sender's Open button
        # still works if the original file is moved or deleted.
        archive_path = SENT_DIR / (
            f"{transfer_id}__{path.name}"
        )

        try:
            shutil.copy2(path, archive_path)
            local_paths[transfer_id] = str(archive_path.resolve())

        except OSError as error:
            root.after(
                0,
                lambda e=error: messagebox.showerror(
                    "Attachment",
                    f"Could not save a local copy:\n{e}"
                )
            )
            return

        start_packet = {
            "type": "attachment_start",
            "transfer_id": transfer_id,
            "chat_type": chat_type,
            "recipient": recipient,
            "kind": attachment_kind,
            "file_name": path.name,
            "file_size": size
        }

        if not send_packet(start_packet):
            return

        try:
            with path.open("rb") as source:
                while True:
                    chunk = source.read(CHUNK_SIZE)

                    if not chunk:
                        break

                    packet = {
                        "type": "attachment_chunk",
                        "transfer_id": transfer_id,
                        "data": base64.b64encode(
                            chunk
                        ).decode("ascii")
                    }

                    if not send_packet(packet):
                        return

            send_packet({
                "type": "attachment_end",
                "transfer_id": transfer_id
            })

        except OSError as error:
            root.after(
                0,
                lambda e=error: messagebox.showerror(
                    "Attachment",
                    str(e)
                )
            )

    threading.Thread(
        target=worker,
        daemon=True
    ).start()


def choose_file():
    path = filedialog.askopenfilename(
        parent=root,
        title="Choose a file"
    )

    if path:
        send_attachment(path, "file")


def choose_image():
    path = filedialog.askopenfilename(
        parent=root,
        title="Choose an image",
        filetypes=[
            (
                "Image files",
                "*.png *.jpg *.jpeg *.gif *.bmp *.webp"
            ),
            ("All files", "*.*")
        ]
    )

    if path:
        send_attachment(path, "image")


send_button.config(command=send_current_message)
entry.bind("<Return>", send_current_message)

file_button.config(command=choose_file)
image_button.config(command=choose_image)

threading.Thread(
    target=receive_messages,
    daemon=True
).start()

refresh_contacts()
choose_chat("Group Chat")


def close_app():
    for transfer in list(active_receives.values()):
        try:
            transfer["file"].close()
        except OSError:
            pass

    try:
        client.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass

    try:
        client_file.close()
    except OSError:
        pass

    try:
        client.close()
    except OSError:
        pass

    root.destroy()


root.protocol("WM_DELETE_WINDOW", close_app)
root.mainloop()
