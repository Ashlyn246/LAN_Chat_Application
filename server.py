import socket
import threading
import json
import database
import os
from datetime import datetime

HOST = "0.0.0.0"
PORT = 5000
DISCOVERY_PORT = 5001

clients = {}                 # socket -> username
send_locks = {}               # socket -> lock, prevents interleaved packets
lock = threading.Lock()
transfers = {}                # transfer_id -> transfer information


def send_message(conn, data):
    with lock:
        conn_lock = send_locks.get(conn)

    if conn_lock is None:
        return False

    try:
        payload = (json.dumps(data, ensure_ascii=False) + "\n").encode("utf-8")
        with conn_lock:
            conn.sendall(payload)
        return True
    except OSError:
        return False


def send_to_user(name, data):
    with lock:
        targets = [conn for conn, username in clients.items() if username == name]

    for conn in targets:
        if send_message(conn, data):
            return True
    return False


def send_contacts():
    contacts = database.get_contacts()

    with lock:
        connections = list(clients.items())
        online = list(clients.values())

    for conn, _ in connections:
        send_message(conn, {
            "type": "contacts",
            "contacts": contacts,
            "online": online
        })


def send_pending_messages(name):
    # Text messages only. Attachments are transferred live and require the
    # recipient to be online; their metadata remains in chat history.
    for row in database.get_pending_messages(name):
        message_id, sender, recipient, text, timestamp = row

        delivered = send_to_user(name, {
            "type": "private",
            "sender": sender,
            "recipient": recipient,
            "message": text,
            "timestamp": timestamp,
            "message_id": message_id,
            "kind": "text",
            "history": True
        })

        if delivered:
            # Client ACK confirms that the message was processed.
            pass


def discover_server():
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    udp.bind(("", DISCOVERY_PORT))

    while True:
        try:
            data, addr = udp.recvfrom(1024)
            if data.decode(errors="ignore") != "LAN_CHAT_DISCOVER":
                continue

            # Determine the server IP on the interface used to reach this client.
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                probe.connect(addr)
                server_ip = probe.getsockname()[0]
            finally:
                probe.close()

            reply = json.dumps({"server_ip": server_ip, "port": PORT})
            udp.sendto(reply.encode(), addr)
        except OSError:
            continue


def get_transfer_targets(sender_conn, chat_type, recipient):
    with lock:
        online_connections = list(clients.items())

    if chat_type == "group":
        return [conn for conn, _ in online_connections]

    recipient_connections = [
        conn for conn, username in online_connections if username == recipient
    ]
    if not recipient_connections:
        return None

    targets = [sender_conn]
    targets.extend(conn for conn in recipient_connections if conn is not sender_conn)
    return targets


def handle_attachment_start(conn, sender, data):
    transfer_id = str(data.get("transfer_id", "")).strip()
    file_name = os.path.basename(str(data.get("file_name", "attachment")).strip())
    file_size = data.get("file_size", 0)
    chat_type = data.get("chat_type", "private")
    kind = data.get("kind", "file")
    recipient = str(data.get("recipient", "")).strip()

    if (
        not transfer_id or not file_name or
        not isinstance(file_size, int) or file_size < 0 or
        file_size > 100 * 1024 * 1024 or
        chat_type not in ("private", "group") or
        kind not in ("file", "image")
    ):
        send_message(conn, {
            "type": "attachment_error",
            "transfer_id": transfer_id,
            "message": "Invalid attachment or file exceeds the 100 MB limit."
        })
        return

    if chat_type == "private":
        if not recipient or recipient == sender:
            return
        database.add_contact(recipient)

    targets = get_transfer_targets(conn, chat_type, recipient)
    if targets is None:
        send_message(conn, {
            "type": "attachment_error",
            "transfer_id": transfer_id,
            "message": f"{recipient} is offline. Attachments can only be sent to online contacts."
        })
        return

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    display_message = f"[{'Image' if kind == 'image' else 'File'}] {file_name}"
    message_id = database.save_message(
        sender,
        recipient if chat_type == "private" else "Group Chat",
        display_message,
        chat_type,
        timestamp,
        kind=kind,
        file_name=file_name,
        file_size=file_size,
        transfer_id=transfer_id
    )

    transfer = {
        "sender_conn": conn,
        "targets": targets,
        "sender": sender,
        "recipient": recipient,
        "chat_type": chat_type,
    }
    with lock:
        transfers[transfer_id] = transfer

    packet = {
        "type": "attachment_start",
        "transfer_id": transfer_id,
        "message_id": message_id,
        "sender": sender,
        "recipient": recipient,
        "chat_type": chat_type,
        "kind": kind,
        "file_name": file_name,
        "file_size": file_size,
        "timestamp": timestamp
    }

    for target in targets:
        send_message(target, packet)

    send_contacts()


def handle_client(conn, addr):
    name = None
    file = None

    try:
        file = conn.makefile("r", encoding="utf-8")
        first_line = file.readline()
        if not first_line:
            return

        name = json.loads(first_line)["name"].strip()
        if not name:
            return

        with lock:
            if name in clients.values():
                send_locks[conn] = threading.Lock()
                send_message(conn, {
                    "type": "error",
                    "message": "This name is already online."
                })
                return
            clients[conn] = name
            send_locks[conn] = threading.Lock()

        database.add_contact(name)
        send_message(conn, {"type": "welcome", "name": name})
        send_contacts()
        send_pending_messages(name)

        for line in file:
            if not line:
                break

            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            action = data.get("type")

            if action == "get_private_history":
                other = data.get("contact", "")
                rows = database.get_private_history(name, other)
                send_message(conn, {
                    "type": "private_history",
                    "contact": other,
                    "messages": [
                        {
                            "id": r[0], "sender": r[1], "recipient": r[2],
                            "message": r[3], "timestamp": r[4],
                            "kind": r[5], "file_name": r[6],
                            "file_size": r[7], "transfer_id": r[8]
                        }
                        for r in rows
                    ]
                })

            elif action == "get_group_history":
                rows = database.get_group_history()
                send_message(conn, {
                    "type": "group_history",
                    "messages": [
                        {
                            "id": r[0], "sender": r[1], "recipient": r[2],
                            "message": r[3], "timestamp": r[4],
                            "kind": r[5], "file_name": r[6],
                            "file_size": r[7], "transfer_id": r[8]
                        }
                        for r in rows
                    ]
                })

            elif action == "ack":
                database.mark_delivered(data.get("message_id", 0))

            elif action == "private":
                recipient = data.get("recipient", "").strip()
                text = data.get("message", "").strip()
                if not recipient or recipient == name or not text:
                    continue

                database.add_contact(recipient)
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                message_id = database.save_message(
                    name, recipient, text, "private", timestamp
                )

                packet = {
                    "type": "private", "sender": name, "recipient": recipient,
                    "message": text, "timestamp": timestamp,
                    "message_id": message_id, "kind": "text"
                }
                send_message(conn, packet)
                send_to_user(recipient, packet)
                send_contacts()

            elif action == "group":
                text = data.get("message", "").strip()
                if not text:
                    continue

                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                message_id = database.save_message(
                    name, "Group Chat", text, "group", timestamp
                )
                packet = {
                    "type": "group", "sender": name, "message": text,
                    "timestamp": timestamp, "message_id": message_id,
                    "kind": "text"
                }
                with lock:
                    targets = list(clients.keys())
                for target in targets:
                    send_message(target, packet)

            elif action == "attachment_start":
                handle_attachment_start(conn, name, data)

            elif action == "attachment_chunk":
                transfer_id = data.get("transfer_id", "")
                with lock:
                    transfer = transfers.get(transfer_id)

                if transfer and transfer["sender_conn"] is conn:
                    for target in transfer["targets"]:
                        send_message(target, data)

            elif action == "attachment_end":
                transfer_id = data.get("transfer_id", "")
                with lock:
                    transfer = transfers.get(transfer_id)

                if transfer and transfer["sender_conn"] is conn:
                    for target in transfer["targets"]:
                        send_message(target, data)
                    with lock:
                        transfers.pop(transfer_id, None)

    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        pass
    finally:
        with lock:
            clients.pop(conn, None)
            send_locks.pop(conn, None)
            # Remove transfers owned by a disconnected sender.
            for transfer_id in [
                tid for tid, item in transfers.items()
                if item["sender_conn"] is conn
            ]:
                transfers.pop(transfer_id, None)

        try:
            if file:
                file.close()
        except OSError:
            pass
        try:
            conn.close()
        except OSError:
            pass

        send_contacts()
        print("Disconnected:", addr, name)


server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind((HOST, PORT))
server.listen()

threading.Thread(target=discover_server, daemon=True).start()
print("LAN Chat server started on port", PORT)

while True:
    conn, addr = server.accept()
    threading.Thread(
        target=handle_client, args=(conn, addr), daemon=True
    ).start()
