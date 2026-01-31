#!/bin/bash

# Log file
LOGFILE="/home/opc/notifyinvest/update_tickers.log"

echo "Starting Ticker Update: $(date)" >> $LOGFILE

# Navigate to project dir
cd /home/opc/notifyinvest

# Run the python script using the venv
./venv/bin/python backend/update_tickers.py >> $LOGFILE 2>&1

res=$?

if [ $res -eq 0 ]; then
    echo "Update successful. Restarting service..." >> $LOGFILE
    sudo systemctl restart notifyinvest-api
    echo "Service restarted." >> $LOGFILE
else
    echo "Update failed with exit code $res. Service NOT restarted." >> $LOGFILE
fi

echo "Finished: $(date)" >> $LOGFILE
echo "-----------------------------------" >> $LOGFILE
