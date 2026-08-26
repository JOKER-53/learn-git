import os

utils_py_path = "api/utils.py"
with open(utils_py_path, "r") as f:
    content = f.read()

content = content.replace("from passlib.context import CryptContext", "from werkzeug.security import generate_password_hash as werkzeug_generate, check_password_hash as werkzeug_check")
content = content.replace("pwd_context = CryptContext(schemes=[\"bcrypt\"], deprecated=\"auto\")", "")
content = content.replace("def get_password_hash(password):\n    return pwd_context.hash(password)", "def get_password_hash(password):\n    return werkzeug_generate(password)")
content = content.replace("def verify_password(plain_password, hashed_password):\n    return pwd_context.verify(plain_password, hashed_password)", "def verify_password(plain_password, hashed_password):\n    return werkzeug_check(hashed_password, plain_password)")

with open(utils_py_path, "w") as f:
    f.write(content)

# We need to add werkzeug to requirements.txt
with open("api/requirements.txt", "a") as f:
    f.write("\nwerkzeug==3.0.3\n")
