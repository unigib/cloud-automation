import json
import os

import boto3
import pymysql
from flask import Flask, redirect, render_template_string, request, url_for


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 4096

PAGE = """
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Student lab guestbook</title></head>
<body>
  <h1>Student lab guestbook</h1>
  <p>Messages are stored in MariaDB on this EC2 instance.</p>
  <form method="post">
    <label for="message">Message (1-280 characters)</label>
    <input id="message" name="message" maxlength="280" required>
    <button type="submit">Add message</button>
  </form>
  <ul>{% for row in messages %}<li>{{ row.message }} — {{ row.created_at }}</li>{% endfor %}</ul>
</body>
</html>
"""


def connect():
    client = boto3.client("secretsmanager", region_name=os.environ["AWS_REGION"])
    secret = json.loads(client.get_secret_value(SecretId=os.environ["SECRET_ARN"])["SecretString"])
    return pymysql.connect(
        host="127.0.0.1",
        user=secret["username"],
        password=secret["password"],
        database="student_lab",
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=5,
    )


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        message = request.form.get("message", "").strip()
        if not 1 <= len(message) <= 280:
            return "Message must be between 1 and 280 characters.", 400
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("INSERT INTO messages (message) VALUES (%s)", (message,))
            connection.commit()
        return redirect(url_for("index"))

    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT message, created_at FROM messages ORDER BY id DESC LIMIT 50")
            messages = cursor.fetchall()
    return render_template_string(PAGE, messages=messages)
