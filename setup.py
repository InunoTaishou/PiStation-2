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
splash_dir = '/home/pi/RetroPie/splashscreens/videos/'

pistation2_service = os.path.dirname(os.path.realpath(__file__)) + '/pistation2.service'
pistation2_splashscreen = os.path.dirname(os.path.realpath(__file__)) + '/PiStation 2 Splashscreen.mp4'
current_splashscreen = ''

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

drives = str(subprocess.check_output('df', shell=True))

if drives.find('/dev/sda1'):
    root = re.search('/dev/root {0,}(\d+) ', drives)
    flash = re.search('/dev/sda1 {0,}(\d+) ', drives)
    flash_drive_dir = re.search('/dev/sda1.*% (.*)', drives)

    if flash and root and flash_drive_dir and flash.group(1) > root.group(1) and \
            not os.path.isdir(flash_drive_dir.group(1) + '/retropie-mount'):
        flash_drive_dir = flash_drive_dir.group(1)

        uuid_type = re.search('/dev/sda1: LABEL=".*" UUID="(.*)" TYPE="(.*)" PARTUUID',
                              str(subprocess.check_output('blkid', shell=True)))
        mounted = False
        fstab_entry = ''

        if uuid_type.lastindex == 2:
            fstab_entry = 'UUID={}\t/home/pi/RetroPie\t{}\tnofail,user,uid=pi,gid=pi\t0\t2\r\n'.format(
                uuid_type.group(1), uuid_type.group(2))

            with open('/etc/fstab', 'r') as fstab_file:
                entries = fstab_file.read().splitlines()

                for entry in entries:
                    if entry and entry.find(fstab_entry) and entry.replace(' ', '')[0] != '#':
                        mounted = True
                    else:
                        mounted = False

        if not mounted:
            user_input = \
                prompt('Larger USB storage device detected ({}gb), would you like to use this for ROM storage? [Y/n] '.format(flash.group(1)))

            if not user_input or user_input.lower()[0] == 'y':
                print('Copying current RetroPie directories and files to flash drive')
                os.system('cp -v -r /home/pi/RetroPie/* ' + flash_drive_dir + '/')

                splash_dir = flash_drive_dir + '/splashscreens/videos/'

                if uuid_type.lastindex == 2:
                    with open('/etc/fstab', 'a') as fstab_file:
                        fstab_file.write(fstab_entry)
                        reboot_required = True
                else:
                    print('Could not get the UUID or format type for the external drive\r\n'
                          'To make this your ROM storage device use this command:\r\n\t'
                          'sudo blkid\r\n'
                          'Copy the UUID and TYPE. Next use\r\n\t'
                          'sudo nano /etc/fstab\r\n'
                          'To edit the fstab file. At the bottom put this (replace YOUR_UUID and YOUR_TYPE with the UUID and TYPE from blkid\r\n\t'
                          'UUID=YOUR_UUID\t/home/pi/RetroPie\tYOUR_TYPE\tnofail,user,uid=pi,gid=pi\t0\t2\r\n'
                          'Then hit CTRL+X, Y (keyboard key Y), then enter. Reboot your system')

if os.path.isfile(pistation2_service):
    print('Setting up the service to start the PiStation 2 monitoring script. '
          '(Monitors the rsync process, controls the fan, and leds)\n')

    os.rename(pistation2_service, '/etc/systemd/system/pistation2.service')
    os.system('systemctl enable pistation2.service')
    reboot_required = True

elif not os.path.isfile('/etc/systemd/system/pistation2.service'):
    print('pistation2.service file does not exist, cannot set service')

with open('/etc/splashscreen.list', 'r') as splashscreen:
    current_splashscreen = splashscreen.read()

if os.path.isfile(pistation2_splashscreen) and current_splashscreen != pistation2_splashscreen:
    user_input = prompt('Would you like to use the PiStation 2 Splashscreen? [Y/n] ')

    if not user_input or user_input.lower()[0] == 'y':
        print('Setting up the PiStation 2 splash screen')

        if os.path.isfile(pistation2_splashscreen):
            if not os.path.isdir(splash_dir):
                os.makedirs(splash_dir)

            os.system('cp \'' +
                      pistation2_splashscreen + '\' '
                      '\'/home/pi/RetroPie/splashscreens/videos/PiStation 2 Splashscreen.mp4\'')

            with open('/etc/splashscreen.list', 'w') as splashscreen:
                splashscreen.write('/home/pi/RetroPie/splashscreens/videos/PiStation 2 Splashscreen.mp4')
        else:
            print('PiStation 2 Splashscreen.mp4 not found, could not set as splashscreen')

elif not os.path.isfile('/home/pi/RetroPie/splashscreens/videos/PiStation 2 Splashscreen.mp4'):
    print('PiStation 2 splash screen not available')

if reboot_required:
    user_input = prompt('A reboot is required to make some things take effect, would you like to reboot now? [y/N] ')

    if user_input and user_input.lower()[0] == 'y':
        os.system('reboot now')

print('PiStation 2 setup has been complete')
