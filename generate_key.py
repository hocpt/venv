from cryptography.fernet import Fernet
key = Fernet.generate_key()
print("Your new encryption key (add this to .env as ENCRYPTION_KEY):")
print(key.decode()) # In key dưới dạng text để dễ copy