# Nội dung file: app/encryption.py
import os
from cryptography.fernet import Fernet, InvalidToken
from flask import current_app # Để lấy key từ config

# Biến global để lưu đối tượng Fernet sau khi khởi tạo
_fernet = None

def _get_fernet():
    """Lấy hoặc khởi tạo đối tượng Fernet từ encryption key trong config."""
    global _fernet
    if _fernet is None:
        # Lấy key từ config (đã được đọc từ .env bởi config.py)
        # >>> QUAN TRỌNG: Đảm bảo biến 'ENCRYPTION_KEY' có trong lớp Config của config.py <<<
        # Ví dụ: ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY') trong config.py
        encryption_key = current_app.config.get('API_ENCRYPTION_KEY')
        if not encryption_key:
            # Log lỗi nghiêm trọng và có thể raise Exception nếu key bắt buộc
            print("CRITICAL ERROR: API_ENCRYPTION_KEY  is not set in Flask config!")
            raise ValueError("Encryption key is missing in application configuration.")
        try:
            # Chuyển key từ string (trong .env) sang bytes
            key_bytes = encryption_key.encode('utf-8')
            _fernet = Fernet(key_bytes)
            print("INFO (encryption): Fernet initialized successfully.") # Log thành công
        except Exception as e:
             print(f"CRITICAL ERROR: Failed to initialize Fernet with the provided key: {e}")
             raise ValueError(f"Invalid encryption key format or value: {e}")
    return _fernet

def encrypt_data(data: str) -> bytes | None:
    """Mã hóa một chuỗi dữ liệu (ví dụ: API key)."""
    if not data:
        return None
    try:
        f = _get_fernet()
        # Dữ liệu cần mã hóa phải là bytes
        data_bytes = data.encode('utf-8')
        encrypted_data = f.encrypt(data_bytes)
        return encrypted_data # Trả về dạng bytes để lưu vào DB (bytea) hoặc base64 sau
    except Exception as e:
        print(f"ERROR during encryption: {e}")
        # Log lỗi chi tiết nếu cần dùng logger
        # logger = current_app.logger if current_app else print
        # logger.error(f"Encryption failed: {e}", exc_info=True)
        return None # Trả về None nếu mã hóa lỗi

def decrypt_data(encrypted_data: bytes | str) -> str | None:
    """Giải mã dữ liệu đã được mã hóa bởi Fernet."""
    if not encrypted_data:
        return None
    try:
        f = _get_fernet()
        # Đảm bảo dữ liệu đầu vào là bytes
        if isinstance(encrypted_data, str):
             # Nếu dữ liệu từ DB là string (ví dụ: lưu dạng text thay vì bytea)
             # Có thể cần decode base64 trước nếu đã encode khi lưu
             encrypted_bytes = encrypted_data.encode('utf-8') # Thử encode trực tiếp
             # Hoặc nếu bạn đã lưu base64:
             # import base64
             # encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode('utf-8'))
        elif isinstance(encrypted_data, bytes):
             encrypted_bytes = encrypted_data
        else:
             print("ERROR: Encrypted data must be bytes or string.")
             return None

        decrypted_bytes = f.decrypt(encrypted_bytes)
        # Chuyển lại thành chuỗi utf-8
        decrypted_string = decrypted_bytes.decode('utf-8')
        return decrypted_string
    except InvalidToken:
         print("ERROR during decryption: Invalid token (key mismatch or data corrupted)")
         return None # Lỗi token không hợp lệ
    except Exception as e:
        print(f"ERROR during decryption: {e}")
        # logger = current_app.logger if current_app else print
        # logger.error(f"Decryption failed: {e}", exc_info=True)
        return None # Trả về None nếu giải mã lỗi