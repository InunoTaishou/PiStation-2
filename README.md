# PiStation-2
PiStation 2

PiStation 2 will set up your Raspberry Pi (with RetroPie installed) as the custom PiStation 2 build! Build includes front LEDs, fan, and monitors rsync, letting you know that ROMs are being copied from the flash drive by flashing the front LEDs.

To install:

    git clone https://github.com/InunoTaishou/PiStation-2.git '/home/pi/PiStation 2'
    cd 'PiStation 2'
    sudo python setup.py
    
The setup script will set everything up for you.

What it's doing:
Setting up the systemctl service, this will start the PiStation 2.py file on boot as a service.
Checking to make sure psutil is installed (module needed to check cpu information)
Installing the custom PiStation 2 splash screen
And sets the external flash drive as the main drive used for all of the ROM storage.
