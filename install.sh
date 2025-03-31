#!/bin/bash

# Clear screen
clear

# Display title
echo -e "\033[1;36m=== 5sim Telegram Bot Installation ===\033[0m"
echo

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo -e "\033[1;31m❌ Python is not installed!\033[0m"
    echo -e "\033[1;33mPlease install Python first:\033[0m"
    echo "sudo apt update"
    echo "sudo apt install python3 python3-pip"
    exit 1
fi

echo -e "\033[1;32m✅ Python is installed\033[0m"
echo

# Install requirements
echo -e "\033[1;36m=== Installing Requirements ===\033[0m"
pip3 install -r requirements.txt
echo

# Get user information
echo -e "\033[1;36m=== Bot Configuration ===\033[0m"
echo -e "\033[1;33mPlease enter the following information:\033[0m"

# Get bot token
read -p "Telegram Bot Token: " BOT_TOKEN

# Get admin ID
read -p "Admin ID (numeric): " ADMIN_ID

# Get webhook URL
read -p "Webhook URL (example: https://your-domain.com): " WEBHOOK_URL

# Get website URL
read -p "Website URL (example: https://your-domain.com): " WEBSITE_URL

# Get 5sim API key
read -p "5sim API Key: " FIVESIM_API_KEY

# Create config.py file
cat > config.py << EOL
BOT_CONFIG = {
    'token': '$BOT_TOKEN',
    'admin_ids': [$ADMIN_ID],
    'webhook_url': '$WEBHOOK_URL',
    'website_url': '$WEBSITE_URL'
}

FIVESIM_CONFIG = {
    'api_key': '$FIVESIM_API_KEY'
}
EOL

# Clear screen
clear

# Display result
echo -e "\033[1;32m✅ Installation completed successfully!\033[0m"
echo
echo -e "\033[1;36m=== Important Information ===\033[0m"
echo -e "\033[1;33mConfiguration file path:\033[0m"
pwd
echo -e "\033[1;33mFile name:\033[0m config.py"
echo
echo -e "\033[1;33mTo edit the file using SFTP, use these commands:\033[0m"
echo "sftp username@your-server-ip"
echo "cd $(pwd)"
echo "get config.py"
echo
echo -e "\033[1;36m=== Starting the Bot ===\033[0m"
echo -e "\033[1;33mStarting the bot...\033[0m"
echo

# Start the bot
python3 bot.py 