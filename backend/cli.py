import os

import core


# ----------------------------- User prompts --------------------------------

def get_valid_directory():
    """Prompts the user for a download folder and ensures it exists."""
    while True:
        directory = input("\nEnter target directory to save MP3 (Leave blank for current folder): ").strip()

        if not directory:
            return "."  # Current directory

        # Clean up path and expand user home directory symbols like ~
        directory = os.path.abspath(os.path.expanduser(directory))

        try:
            if not os.path.exists(directory):
                os.makedirs(directory)
                print(f"📁 Created folder: {directory}")
            return directory
        except Exception as e:
            print(f"❌ Invalid directory or permission denied. Error: {e}. Please try again.")

def get_valid_bitrate():
    """Prompts the user for a bitrate and validates the input."""
    print("\nSelect your desired MP3 quality (bitrate):")
    print("1. 128 kbps (Standard quality / smaller file)")
    print("2. 192 kbps (High quality - Recommended)")
    print("3. 256 kbps (Very high quality)")
    print("4. 320 kbps (Highest quality / larger file)")
    print("5. Custom bitrate")

    while True:
        choice = input("Enter choice (1-5) or directly enter a value (e.g., 256): ").strip()

        if choice == '1':
            return '128'
        elif choice == '2':
            return '192'
        elif choice == '3':
            return '256'
        elif choice == '4':
            return '320'
        elif choice == '5':
            custom = input("Enter custom bitrate in kbps (e.g., 160): ").strip()
            if custom.isdigit():
                return custom
        elif choice.isdigit():
            return choice

        print("❌ Invalid input. Please enter a number between 1-5 or a valid numeric bitrate.")

def get_yes_no(prompt, default=True):
    """Simple yes/no prompt; Enter accepts the default."""
    hint = "Y/n" if default else "y/N"
    while True:
        answer = input(f"{prompt} [{hint}]: ").strip().lower()
        if not answer:
            return default
        if answer in ('y', 'yes'):
            return True
        if answer in ('n', 'no'):
            return False
        print("❌ Please answer y or n.")


def get_download_mode():
    """Asks whether to download MP3 audio, HEVC video, or just the English captions."""
    print("\nWhat would you like to download?")
    print("1. Audio (tagged MP3 with cover art)")
    print("2. Video (MP4)")
    print("3. Captions only (English .srt + .txt transcript)")

    modes = {'1': core.MODE_MP3, '2': core.MODE_VIDEO, '3': core.MODE_CAPTIONS}
    while True:
        choice = input("Enter choice (1-3): ").strip()
        if choice in modes:
            return modes[choice]
        print("❌ Invalid input. Please enter 1, 2 or 3.")

def get_valid_resolution(heights):
    """
    Asks for a maximum video resolution. Returns an int height cap, or None for best.
    heights: what a single video offers; empty (playlist) offers the standard tiers instead.
    """
    options = [(None, "Best available")]
    if heights:
        options += [(h, f"{h}p") for h in heights]
    else:
        options += [(h, f"{h}p or the best below it") for h in core.RESOLUTION_TIERS]

    print("\nSelect your desired video resolution:")
    if not heights:
        print("(Each video downloads at the chosen resolution, or the best one it has below it.)")
    for i, (_, text) in enumerate(options, start=1):
        print(f"{i}. {text}")

    while True:
        choice = input(f"Enter choice (1-{len(options)}): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return options[int(choice) - 1][0]
        print(f"❌ Invalid input. Please enter a number between 1 and {len(options)}.")


if __name__ == "__main__":
    url = input("Enter YouTube Video or Playlist URL: ").strip()
    if not url:
        print("❌ URL cannot be empty.")
        raise SystemExit(1)

    mode = get_download_mode()

    try:
        print("\n🔎 Reading the link...")
        heights = core.preview_youtube(url)['heights'] if mode == core.MODE_VIDEO else []
    except (ValueError, RuntimeError) as e:
        print(f"❌ {e}")
        raise SystemExit(1)

    output_folder = get_valid_directory()
    max_height, kbps, extra_metadata, captions, hevc = None, '192', False, False, False

    if mode == core.MODE_VIDEO:
        max_height = get_valid_resolution(heights)
        hevc = get_yes_no(
            "\nRe-encode the video to HEVC/x265? Smaller files, but much slower", default=False)
    if mode != core.MODE_CAPTIONS:
        kbps = get_valid_bitrate()
    if mode != core.MODE_CAPTIONS:
        captions = get_yes_no("\nAlso save English captions (.srt + .txt transcript)?", default=False)
    if mode == core.MODE_MP3:
        extra_metadata = get_yes_no(
            "\nFetch extra metadata (genre, BPM, label, ISRC, lyrics, ...)? Only suits music; "
            "may mismatch other videos. Slower", default=False)

    core.download_youtube(url, kbps, output_folder, enrich=extra_metadata,
                          mode=mode, max_height=max_height, captions=captions, hevc=hevc)
