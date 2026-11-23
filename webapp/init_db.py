import json
import os
import re
import subprocess

import boto3


def main() -> None:
    client = boto3.client("secretsmanager", region_name=os.environ["AWS_REGION"])
    secret = json.loads(client.get_secret_value(SecretId=os.environ["SECRET_ARN"])["SecretString"])
    username = secret["username"]
    password = secret["password"]
    if username != "labuser" or not re.fullmatch(r"[A-Za-z0-9]+", password):
        raise ValueError("Database secret has an invalid username or password")

    sql = f"""
CREATE DATABASE IF NOT EXISTS student_lab CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '{username}'@'127.0.0.1' IDENTIFIED BY '{password}';
ALTER USER '{username}'@'127.0.0.1' IDENTIFIED BY '{password}';
GRANT SELECT, INSERT ON student_lab.* TO '{username}'@'127.0.0.1';
CREATE TABLE IF NOT EXISTS student_lab.messages (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    message VARCHAR(280) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""
    subprocess.run(["mariadb", "--protocol=socket", "-u", "root"], input=sql, text=True, check=True)


if __name__ == "__main__":
    main()
