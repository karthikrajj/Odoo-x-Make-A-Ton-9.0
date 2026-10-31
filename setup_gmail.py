"""Terminal alternative to the graphical Gmail setup window."""

import getpass

from renewsure.email_settings import defaults, save_connection


def main():
    print("Connect RenewSure to Gmail using a Google app password.")
    print("Google help: https://support.google.com/accounts/answer/185833")
    print("No email is sent by this setup check. Never enter credentials in chat.")
    default_sender, default_url = defaults()
    sender = (
        input(f"Sending Gmail address [{default_sender}]: ").strip() or default_sender
    ).lower()
    secret = getpass.getpass("Gmail app password (hidden): ")
    base = input(f"Application URL [{default_url}]: ").strip() or default_url
    try:
        save_connection(sender, secret, base)
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc)) from None
    print(
        "Gmail authentication succeeded. Configuration saved locally. Restart RenewSure to enable delivery."
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nSetup cancelled; existing configuration preserved.")
