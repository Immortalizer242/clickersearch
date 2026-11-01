import io
import json
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from zipfile import ZIP_DEFLATED, ZipFile

import cv2
import mss
import numpy as np
import pyautogui


class ImageClicker:
    def __init__(self, root):
        self.root = root
        self.root.title("Multi-Image Match Clicker")

        # Each item is {"name": filename, "image": grayscale OpenCV image}
        # The list order is the priority order.
        self.templates = []
        self.running = False

        self.threshold = tk.DoubleVar(value=0.90)
        self.min_scale = tk.DoubleVar(value=0.50)
        self.max_scale = tk.DoubleVar(value=1.50)

        profile_buttons = tk.Frame(root)
        profile_buttons.pack(padx=12, pady=(10, 4), fill="x")

        tk.Button(
            profile_buttons, text="Add images", command=self.add_images
        ).pack(side="left", padx=3)
        tk.Button(
            profile_buttons, text="Save profile", command=self.save_profile
        ).pack(side="left", padx=3)
        tk.Button(
            profile_buttons, text="Load profile", command=self.load_profile
        ).pack(side="left", padx=3)

        tk.Label(
            root,
            text="Image priority (top = highest):"
        ).pack(anchor="w", padx=12, pady=(8, 0))

        self.image_list = tk.Listbox(root, width=52, height=7)
        self.image_list.pack(padx=12, pady=4, fill="both")

        priority_buttons = tk.Frame(root)
        priority_buttons.pack(padx=12, pady=2)

        tk.Button(
            priority_buttons, text="Move up", command=lambda: self.move_item(-1)
        ).pack(side="left", padx=3)
        tk.Button(
            priority_buttons, text="Move down", command=lambda: self.move_item(1)
        ).pack(side="left", padx=3)
        tk.Button(
            priority_buttons, text="Remove selected", command=self.remove_selected
        ).pack(side="left", padx=3)

        tk.Label(root, text="Match threshold (0–1):").pack()
        tk.Scale(
            root,
            from_=0.60,
            to=0.99,
            resolution=0.01,
            orient="horizontal",
            variable=self.threshold,
        ).pack(fill="x", padx=12)

        scale_row = tk.Frame(root)
        scale_row.pack(fill="x", padx=12, pady=4)

        tk.Label(scale_row, text="Scale range:").pack(side="left")
        tk.Entry(scale_row, textvariable=self.min_scale, width=6).pack(
            side="left", padx=(6, 2)
        )
        tk.Label(scale_row, text="to").pack(side="left")
        tk.Entry(scale_row, textvariable=self.max_scale, width=6).pack(
            side="left", padx=2
        )

        self.status = tk.Label(root, text="Add images or load a profile.")
        self.status.pack(padx=12, pady=8)

        controls = tk.Frame(root)
        controls.pack(pady=(0, 10))

        self.start_button = tk.Button(
            controls, text="Start", command=self.start
        )
        self.start_button.pack(side="left", padx=4)

        self.stop_button = tk.Button(
            controls, text="Stop", command=self.stop, state="disabled"
        )
        self.stop_button.pack(side="left", padx=4)

        root.bind("<Escape>", lambda _event: self.stop())

    def refresh_list(self, selected_index=None):
        self.image_list.delete(0, tk.END)
        for item in self.templates:
            self.image_list.insert(tk.END, item["name"])

        if selected_index is not None and self.templates:
            selected_index = max(0, min(selected_index, len(self.templates) - 1))
            self.image_list.selection_set(selected_index)
            self.image_list.activate(selected_index)

    def add_images(self):
        paths = filedialog.askopenfilenames(
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp")]
        )
        added = 0

        for path in paths:
            image = cv2.imread(path)
            if image is None:
                continue

            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            self.templates.append({
                "name": Path(path).name,
                "image": gray,
            })
            added += 1

        self.refresh_list()
        self.status.config(
            text=f"Added {added} image(s); {len(self.templates)} total."
        )

    def remove_selected(self):
        selected = list(self.image_list.curselection())
        for index in reversed(selected):
            del self.templates[index]

        self.refresh_list()
        self.status.config(text=f"{len(self.templates)} image(s) loaded.")

    def move_item(self, direction):
        selected = self.image_list.curselection()
        if not selected:
            return

        index = selected[0]
        new_index = index + direction
        if not 0 <= new_index < len(self.templates):
            return

        self.templates[index], self.templates[new_index] = (
            self.templates[new_index],
            self.templates[index],
        )
        self.refresh_list(new_index)

    def save_profile(self):
        if not self.templates:
            messagebox.showwarning("No images", "Add images before saving a profile.")
            return

        path = filedialog.asksaveasfilename(
            title="Save profile",
            defaultextension=".zip",
            filetypes=[("Image Clicker profile", "*.zip")],
        )
        if not path:
            return

        try:
            profile = {
                "version": 1,
                "threshold": self.threshold.get(),
                "min_scale": self.min_scale.get(),
                "max_scale": self.max_scale.get(),
                "images": [],
            }

            with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
                for index, item in enumerate(self.templates):
                    # Store each imported image inside the profile archive.
                    success, encoded = cv2.imencode(".png", item["image"])
                    if not success:
                        raise ValueError(f"Could not encode {item['name']}")

                    image_entry = f"images/{index}.png"
                    archive.writestr(image_entry, encoded.tobytes())
                    profile["images"].append({
                        "name": item["name"],
                        "file": image_entry,
                    })

                archive.writestr(
                    "profile.json",
                    json.dumps(profile, indent=2),
                )

            self.status.config(text=f"Profile saved: {Path(path).name}")

        except Exception as error:
            messagebox.showerror("Save failed", str(error))

    def load_profile(self):
        path = filedialog.askopenfilename(
            title="Load profile",
            filetypes=[("Image Clicker profile", "*.zip")],
        )
        if not path:
            return

        try:
            with ZipFile(path, "r") as archive:
                profile = json.loads(archive.read("profile.json"))
                loaded_templates = []

                for item in profile["images"]:
                    raw = archive.read(item["file"])
                    image = cv2.imdecode(
                        np.frombuffer(raw, dtype=np.uint8),
                        cv2.IMREAD_GRAYSCALE,
                    )
                    if image is None:
                        raise ValueError(f"Could not read {item['name']}")

                    loaded_templates.append({
                        "name": item["name"],
                        "image": image,
                    })

            # Replace the current list with the profile's saved priority order.
            self.templates = loaded_templates
            self.threshold.set(profile.get("threshold", 0.90))
            self.min_scale.set(profile.get("min_scale", 0.50))
            self.max_scale.set(profile.get("max_scale", 1.50))

            self.refresh_list()
            self.status.config(
                text=f"Loaded profile with {len(self.templates)} image(s)."
            )

        except Exception as error:
            messagebox.showerror("Load failed", f"Could not load profile:\n{error}")

    def start(self):
        if not self.templates:
            messagebox.showwarning("No images", "Add images or load a profile first.")
            return

        try:
            low = float(self.min_scale.get())
            high = float(self.max_scale.get())
            if low <= 0 or high < low:
                raise ValueError
        except (ValueError, tk.TclError):
            messagebox.showerror(
                "Invalid scale range",
                "Enter positive numbers, with the maximum at least as large as the minimum.",
            )
            return

        self.running = True
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        threading.Thread(target=self.scan_screen, daemon=True).start()

    def stop(self):
        self.running = False
        self.start_button.config(state="normal")
        self.stop_button.config(state="disabled")
        self.status.config(text="Stopped.")

    def scan_screen(self):
        low = float(self.min_scale.get())
        high = float(self.max_scale.get())
        scale_steps = np.linspace(low, high, num=11)

        # Take a snapshot so list changes cannot alter the active scan.
        templates = list(self.templates)
        threshold = float(self.threshold.get())

        with mss.mss() as screen:
            monitor = screen.monitors[1]

            while self.running:
                frame = np.array(screen.grab(monitor))
                gray = cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY)

                # Check images in priority order. Click the first one that matches.
                for item in templates:
                    template = item["image"]
                    original_h, original_w = template.shape
                    found = None

                    for scale in scale_steps:
                        new_w = int(original_w * scale)
                        new_h = int(original_h * scale)

                        if (
                            new_w < 1
                            or new_h < 1
                            or new_w > gray.shape[1]
                            or new_h > gray.shape[0]
                        ):
                            continue

                        resized = cv2.resize(
                            template,
                            (new_w, new_h),
                            interpolation=(
                                cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
                            ),
                        )

                        result = cv2.matchTemplate(
                            gray, resized, cv2.TM_CCOEFF_NORMED
                        )
                        _min_val, max_val, _min_loc, max_loc = cv2.minMaxLoc(result)

                        if max_val >= threshold:
                            found = (max_val, max_loc, new_w, new_h)
                            break

                    if found:
                        confidence, location, match_w, match_h = found
                        x = monitor["left"] + location[0] + match_w // 2
                        y = monitor["top"] + location[1] + match_h // 2

                        pyautogui.click(x, y)
                        name = item["name"]
                        self.root.after(
                            0,
                            lambda n=name, c=confidence: self.status.config(
                                text=f"Clicked {n} (confidence {c:.2f})."
                            ),
                        )
                        time.sleep(1)
                        break

                time.sleep(0.2)

        self.root.after(0, self.stop)


root = tk.Tk()
app = ImageClicker(root)
root.mainloop()
