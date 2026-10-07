import os


IMAGE_DIR = r"C:\Users\shaik\Downloads\ProjectWork\smart-inventory-system\cv_pipeline\dataset\images"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".heic", ".heif"}


def main():
    files = []

    for filename in os.listdir(IMAGE_DIR):
        path = os.path.join(IMAGE_DIR, filename)

        if os.path.isfile(path):
            extension = os.path.splitext(filename)[1].lower()

            if extension in IMAGE_EXTENSIONS:
                files.append(filename)

    files.sort()

    if not files:
        print("No images found.")
        return

    print(f"Found {len(files)} images.")

    # Temporary names prevent filename collisions.
    temporary_files = []

    for index, filename in enumerate(files):
        old_path = os.path.join(IMAGE_DIR, filename)
        temp_name = f"__temp_{index:04d}{os.path.splitext(filename)[1].lower()}"
        temp_path = os.path.join(IMAGE_DIR, temp_name)

        os.rename(old_path, temp_path)
        temporary_files.append((temp_name, os.path.splitext(filename)[1].lower()))

    # Rename sequentially.
    for index, (temp_name, extension) in enumerate(temporary_files, start=1):
        old_path = os.path.join(IMAGE_DIR, temp_name)
        new_name = f"box-{index:03d}{extension}"
        new_path = os.path.join(IMAGE_DIR, new_name)

        os.rename(old_path, new_path)

    print("Renaming complete.")
    print(f"Images renamed: box-001 to box-{len(files):03d}")


if __name__ == "__main__":
    main()