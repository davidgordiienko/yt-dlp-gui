# YT-DLP GUI
A simple Windows GUI for YT-DLP made in Python using Tkinter.
## Usage and installation
### Users (99% of people)
Go to the [Releases](https://github.com/davidgordiienko/yt-dlp-gui/releases) tab and download the EXE
### Developers, advanced users, and people who want to run this using Python
Clone (download) the repo and also download yt-dlp and ffmpeg EXEs and place them in the project's root directory. Make sure they are named `yt-dlp.exe` and `ffmpeg.exe`. From there, you can run the file with Python or within your IDE.
## How the app works
The app automatically detects your clipboard and pastes it into the YouTube URL field. Then you can choose to download it as MP4 best quality or MP3 best quality. The app automatically checks for yt-dlp updates on startup so the app updates critical components itself and you don't have to redownload things. If there is ever a major update then you will have to re-download the exe from GitHub, so I'd recommend making sure you get notifications for new releases by watching this repo.