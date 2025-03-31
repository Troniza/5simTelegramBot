# 5sim Telegram Bot

A Telegram bot for managing 5sim services with admin panel and user management features.

## Features

- User management system
- Admin panel with statistics
- Transaction history
- Channel management
- Balance management
- Card payment system
- Broadcast messages


## Requirements

- Python 3.8 or higher
- pip (Python package manager)
- Linux server (Ubuntu/Debian recommended)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/Troniza/5simTelegramBot.git
```
1.1
```bash
cd 5simTelegramBot
```
2. Make the installation script executable:
```bash
chmod +x install.sh
```

3. Run the installation script:
```bash
./install.sh
```

4. Follow the prompts to enter:
   - Telegram Bot Token
   - Admin ID (numeric)
   - Webhook URL
   - Website URL
   - 5sim API Key

## Configuration

The bot configuration is stored in `config.py`. You can edit this file manually or use SFTP to modify it:

```bash
sftp username@your-server-ip
cd /path/to/bot
get config.py
```

## Running the Bot

The bot will start automatically after installation. To start it manually:

```bash
python3 bot.py
```


## Support

For support, please create an issue in the GitHub repository or contact the administrator.

## License

This project is licensed under the MIT License - see the LICENSE file for details. 