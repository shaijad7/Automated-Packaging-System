import os
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pillow_heif = None


IMAGE_DIR = r"C:\Users\shaik\Downloads\ProjectWork\smart-inventory-system\cv_pipeline\dataset\images"

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".webp",
    ".heic",
    ".heif",
}


class ImageReviewer:
    def __init__(self, root):
        self.root = root
        self.root.title("Dataset Image Reviewer")
        self.root.geometry("1100x850")

        self.images = self.get_images()
        self.index = 0
        self.photo = None

        self.image_label = tk.Label(
            root,
            text="Loading...",
            font=("Arial", 16)
        )
        self.image_label.pack(expand=True, fill="both", padx=10, pady=10)

        self.info_label = tk.Label(
            root,
            font=("Arial", 13)
        )
        self.info_label.pack(pady=5)

        self.help_label = tk.Label(
            root,
            text="K = KEEP     D = DELETE     Q = QUIT",
            font=("Arial", 12)
        )
        self.help_label.pack(pady=5)

        root.bind("<KeyPress-k>", self.keep_image)
        root.bind("<KeyPress-K>", self.keep_image)

        root.bind("<KeyPress-d>", self.delete_image)
        root.bind("<KeyPress-D>", self.delete_image)

        root.bind("<KeyPress-q>", self.quit_app)
        root.bind("<KeyPress-Q>", self.quit_app)

        self.show_image()

    def get_images(self):
        if not os.path.exists(IMAGE_DIR):
            messagebox.showerror(
                "Error",
                f"Image directory does not exist:\n\n{IMAGE_DIR}"
            )
            return []

        files = []

        for filename in os.listdir(IMAGE_DIR):
            path = os.path.join(IMAGE_DIR, filename)

            if not os.path.isfile(path):
                continue

            extension = os.path.splitext(filename)[1].lower()

            if extension in IMAGE_EXTENSIONS:
                files.append(filename)

        return sorted(files, key=str.lower)

    def show_image(self):
        if self.index >= len(self.images):
            self.image_label.config(
                image="",
                text="Finished reviewing all images."
            )

            self.info_label.config(
                text=f"Remaining images: {len(self.images)}"
            )

            return

        filename = self.images[self.index]
        path = os.path.join(IMAGE_DIR, filename)

        try:
            with Image.open(path) as image:
                image.load()

                display_image = image.copy()
                display_image.thumbnail((1050, 700))

            self.photo = ImageTk.PhotoImage(display_image)

            self.image_label.config(
                image=self.photo,
                text=""
            )

            self.info_label.config(
                text=f"{self.index + 1} / {len(self.images)}    {filename}"
            )

            self.root.focus_force()

        except Exception as error:
            self.image_label.config(
                image="",
                text=f"Cannot display image:\n{filename}"
            )

            self.info_label.config(
                text=str(error)
            )

    def keep_image(self, event=None):
        if self.index >= len(self.images):
            return

        self.index += 1
        self.show_image()

    def delete_image(self, event=None):
        if self.index >= len(self.images):
            return

        filename = self.images[self.index]
        path = os.path.join(IMAGE_DIR, filename)

        confirm = messagebox.askyesno(
            "Confirm Delete",
            f"Delete this image?\n\n{filename}"
        )

        if not confirm:
            return

        try:
            os.remove(path)

            self.images.pop(self.index)

            self.show_image()

        except Exception as error:
            messagebox.showerror(
                "Delete Error",
                f"Could not delete:\n\n{filename}\n\n{error}"
            )

    def quit_app(self, event=None):
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    ImageReviewer(root)
    root.mainloop()