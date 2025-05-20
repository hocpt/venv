import os
import sys
# Thêm thư mục gốc của dự án vào sys.path để import app
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '.')) # Sửa thành '.' nếu test_db_queries.py ở gốc
sys.path.insert(0, project_root)

from app import create_app # Giả sử bạn có hàm create_app trong app/__init__.py
from app.database import get_screen_definitions_for_app, get_db_connection # Import hàm bạn muốn test

app = create_app() # Tạo instance của app để có app_context

def test_get_screen_defs():
    with app.app_context(): # Chạy trong app_context
        print("--- Testing get_screen_definitions_for_app ---")

        # Test trường hợp có activity_name
        defs_with_activity = get_screen_definitions_for_app("com.example.app", ".MainActivity")
        print("\nDefinitions for com.example.app, .MainActivity:")
        if defs_with_activity:
            for definition in defs_with_activity:
                print(definition)
        else:
            print("None found or error.")

        # Test trường hợp chỉ có app_name (sẽ lấy cả NULL activity và có thể là cả cái có activity nếu logic của bạn gộp)
        # Logic hiện tại của bạn sẽ ưu tiên cái có activity, nếu không có thì lấy cái null activity
        # Nếu muốn lấy cả hai, bạn cần sửa query hoặc gọi 2 lần và gộp kết quả.
        # Hiện tại, hàm của bạn sẽ tìm cái có activity trước, nếu không có thì tìm cái null activity,
        # và nếu activity_name được cung cấp nhưng không có kết quả, nó sẽ thử tìm với activity_name là NULL.

        print("\nDefinitions for com.example.app (activity_name = None, nên chỉ lấy record có activity_name là NULL):")
        defs_app_only_explicit_null = get_screen_definitions_for_app("com.example.app", None)
        if defs_app_only_explicit_null:
            for definition in defs_app_only_explicit_null:
                print(definition)
        else:
            print("None found or error for explicit null activity.")

        print("\nDefinitions for com.example.app (activity_name = '.NonExistentActivity', sẽ fallback tìm activity_name là NULL):")
        defs_app_non_existent_activity = get_screen_definitions_for_app("com.example.app", ".NonExistentActivity")
        if defs_app_non_existent_activity:
            for definition in defs_app_non_existent_activity:
                print(definition) # Nên thấy cái 'ex_login_gen_v1'
        else:
            print("None found or error for non-existent activity (fallback check).")


        print("\nDefinitions for non_existent.app:")
        defs_no_app = get_screen_definitions_for_app("non_existent.app")
        print(defs_no_app if defs_no_app else "None found or error.")


if __name__ == "__main__":
    # Test kết nối DB trước
    with app.app_context():
        conn_test = get_db_connection()
        if conn_test:
            print("Kết nối PostgreSQL thành công!")
            conn_test.close()
        else:
            print("Không thể kết nối PostgreSQL!")

    test_get_screen_defs()