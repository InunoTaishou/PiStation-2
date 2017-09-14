#!/usr/bin/env python

import os
import sys
import re
import subprocess
import importlib

if sys.version_info[0] < 3:
    prompt = raw_input
else:
    prompt = input

reboot_required = False

pistation2_service = os.path.dirname(os.path.realpath(__file__)) + '/pistation2.service'
pistation2_splashscreen = os.path.dirname(os.path.realpath(__file__)) + '/PiStation 2 Splashscreen.mp4'


try:
    __import__('psutil')
except ImportError:
    user_input = prompt(
        'psutil is required to make the PiStation 2.py file function correctly. Would you like to install it? [Y/n] ')

    if not user_input or user_input.lower()[0] == 'y':
        print('Getting build-essential, python-dev, and python-pip libraries')
        os.system('apt-get install build-essential python-dev python-pip -y')

        print('Getting psutil library')
        os.system('sudo pip install psutil')

if os.path.isfile(pistation2_service):
    print('Setting up the service to start the PiStation 2 monitoring script. '
          'Monitors the rsync process, controls the fan, and leds\n')

    os.rename(pistation2_service, '/etc/systemd/system/pistation2.service')
    os.system('systemctl enable pistation2.service')
    reboot_required = True
elif not os.path.isfile('/etc/systemd/system/pistation2.service'):
    print('pistation2.service file does not exist, cannot set service')

if os.path.isfile(pistation2_splashscreen):
    user_input = prompt('Would you like to use the PiStation 2 Splashscreen? [Y/n] ')
    if not user_input or user_input.lower()[0] == 'y':
        print('Setting up the PiStation 2 splash screen')

        if not os.path.isdir('/home/pi/RetroPie/splashscreens/videos/'):
            os.makedirs('/home/pi/RetroPie/splashscreens/videos/')

        os.rename(pistation2_splashscreen, '/home/pi/RetroPie/splashscreens/videos/PiStation 2 Splashscreen.mp4')

        with open('/etc/splashscreen.list', 'w') as splashscreen:
            splashscreen.write('/home/pi/RetroPie/splashscreens/videos/PiStation 2 Splashscreen.mp4')

elif not os.path.isfile('/home/pi/RetroPie/splashscreens/videos/PiStation 2 Splashscreen.mp4'):
    print('PiStation 2 splash screen not available')

drives = subprocess.check_output('df -h', shell=True).replace(' ', '')

if drives.find('/dev/sda1'):
    root = re.search('/dev/root(\d+)G*', drives)
    flash = re.search('/dev/sda1(\d+)G', drives)
    flash_dir = re.search('/dev/sda1.*%(.*)', drives)
    if flash and root and flash_dir:
        if flash.group(1) > root.group(1) and not os.path.isdir(flash_dir.group(1) + '/retropie-mount'):
            user_input = \
                prompt('Larger USB storage device detected ({}gb), '
                       'would you like to use this for ROM storage? [Y/n] ', flash.group(1))
            if user_input or user_input.lower()[0] == 'y':
                os.makedirs(flash + '/retropie-mount')

                print('Using RetroPie easy mount method. '
                      'RetroPie will automatically copy the '
                      'RetroPie folder and contents to flash drive. '
                      'You may need to reboot to start the copying. '
                      'Please refer to the github wiki page for more information: '
                      'https://github.com/RetroPie/RetroPie-Setup/wiki/Running-ROMs-from-a-USB-drive')


if reboot_required:
    if prompt('A reboot is required to make some things take effect, would you like to reboot now? ') == 'y':
        os.system('reboot now')
