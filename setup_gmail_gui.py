"""User-operated Gmail connection window. No credentials are printed or sent to chat."""

import threading
import tkinter as tk
import webbrowser
from tkinter import ttk

from renewsure.email_settings import defaults, save_connection


def main():
    root = tk.Tk()
    root.title("RenewSure — Gmail setup (fixed layout)")
    root.geometry(f"650x{max(420, min(680, root.winfo_screenheight() - 120))}")
    root.minsize(420, 360)
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TFrame", background="#f6f7fa")
    style.configure("TLabel", background="#f6f7fa", font=("Segoe UI", 11))
    style.configure("TButton", font=("Segoe UI", 10), padding=9)
    style.configure("Title.TLabel", font=("Segoe UI", 21, "bold"), foreground="#714b67")
    # Keep the action/status footer visible; only instructions and fields scroll.
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)
    canvas = tk.Canvas(root, background="#f6f7fa", highlightthickness=0)
    scrollbar = ttk.Scrollbar(root, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.grid(row=0, column=0, sticky="nsew")
    scrollbar.grid(row=0, column=1, sticky="ns")
    frame = ttk.Frame(canvas, padding=20)
    window = canvas.create_window((0, 0), window=frame, anchor="nw")
    footer = ttk.Frame(root, padding=(20, 10))
    footer.grid(row=1, column=0, columnspan=2, sticky="ew")

    def resize(event):
        canvas.itemconfigure(window, width=event.width)
        for widget in frame.winfo_children():
            if isinstance(widget, ttk.Label):
                widget.configure(wraplength=max(250, event.width - 45))

    def update_scroll(event):
        canvas.configure(scrollregion=canvas.bbox("all"))

    canvas.bind("<Configure>", resize)
    frame.bind("<Configure>", update_scroll)
    root.bind(
        "<MouseWheel>",
        lambda event: canvas.yview_scroll(-int(event.delta / 120), "units"),
    )
    ttk.Label(frame, text="Connect Gmail to RenewSure", style="Title.TLabel").pack(
        anchor="w"
    )
    ttk.Label(
        frame,
        text="Complete these steps yourself to keep control of your Google account.",
        wraplength=580,
    ).pack(anchor="w", pady=(8, 18))
    ttk.Label(
        frame, text="1. Secure your Google account", font=("Segoe UI", 12, "bold")
    ).pack(anchor="w")
    ttk.Label(
        frame,
        text="If you shared your normal Gmail password in chat, change it first.\nThen turn on 2-Step Verification in your Google account.",
        wraplength=580,
    ).pack(anchor="w", pady=5)
    ttk.Button(
        frame,
        text="Open Google account security",
        command=lambda: webbrowser.open("https://myaccount.google.com/security"),
    ).pack(anchor="w")
    ttk.Label(
        frame, text="2. Create an app password", font=("Segoe UI", 12, "bold")
    ).pack(anchor="w", pady=(16, 5))
    ttk.Label(
        frame,
        text="Open the page, sign in if asked, and name the app RenewSure.\nGoogle will show a 16-character password. Copy it.",
        wraplength=580,
    ).pack(anchor="w")
    ttk.Button(
        frame,
        text="Open Google App Passwords",
        command=lambda: webbrowser.open("https://myaccount.google.com/apppasswords"),
    ).pack(anchor="w", pady=6)
    ttk.Label(frame, text="3. Connect this app", font=("Segoe UI", 12, "bold")).pack(
        anchor="w", pady=(12, 5)
    )
    ttk.Label(frame, text="Sending email").pack(anchor="w")
    sender = tk.StringVar(value=defaults()[0])
    ttk.Entry(frame, textvariable=sender, width=55).pack(fill="x", pady=(3, 8))
    ttk.Label(frame, text="App password — paste it here, never in chat").pack(
        anchor="w"
    )
    secret = tk.StringVar()
    entry = ttk.Entry(frame, textvariable=secret, show="●", width=55)
    entry.pack(fill="x", pady=3)
    status = tk.StringVar(
        value="This checks Gmail authentication. No email is sent by this setup check."
    )
    label = ttk.Label(footer, textvariable=status, wraplength=570)
    label.pack(anchor="w", pady=(2, 8))
    footer.bind(
        "<Configure>",
        lambda event: label.configure(wraplength=max(250, event.width - 40)),
    )

    def finish(error=None):
        save.config(state="normal")
        if error:
            status.set(error)
        else:
            secret.set("")
            entry.config(state="disabled")
            save.config(state="disabled")
            status.set(
                "Connected successfully. You can close this window. Tell the assistant “Gmail connected” so it can restart RenewSure and verify delivery."
            )

    def connect():
        address = sender.get().strip().lower()
        password = secret.get()
        save.config(state="disabled")
        status.set("Checking your encrypted Gmail connection…")

        def work():
            try:
                save_connection(address, password)
            except (ValueError, OSError) as exc:
                root.after(0, lambda message=str(exc): finish(message))
            else:
                root.after(0, finish)

        threading.Thread(target=work, daemon=True).start()

    save = ttk.Button(footer, text="Connect Gmail securely", command=connect)
    save.pack(fill="x", pady=4)
    entry.bind(
        "<FocusIn>", lambda event: root.after_idle(lambda: canvas.yview_moveto(1.0))
    )
    root.mainloop()


if __name__ == "__main__":
    main()
