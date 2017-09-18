#!/usr/bin/python
# -*- coding: utf-8 -*-

import RPi.GPIO as GPIO
from time import sleep, time
from datetime import datetime
import threading
import subprocess
import os
import psutil
import sys

if sys.version_info[0] < 3:
    from Queue import Queue, Empty
else:
    from queue import Queue, Empty

# Using Pin # 5 (GPIO03 (SCLI, I2C)) to restart, shutdown, and turn on the pi
restart_shutdown_pin = 5
# Using pin # 37 to set the fan to high, pin 35 for the low speed
fan_pin_high = 37
fan_pin_low = 35
# Using pin 8 for the front LEDs
front_led_pin = 8

FAN_OFF = 0
FAN_LOW = 1
FAN_HIGH = 2

GPIO.setmode(GPIO.BOARD)
GPIO.setwarnings(False)


class PrintQueue:
    def __init__(self):
        self.queue = Queue()
        self.__printing = True
        self.__stop_event = threading.Event()

        threading.Thread(name='PrintQueue', target=self.__printer).start()

    def queue_add(self, text):
        self.queue.put_nowait(text)

    def close(self):
        self.queue.join()
        self.__printing = False

    def __printer(self):
        while self.__printing:
            try:
                text = self.queue.get()
                print(text)
                self.queue.task_done()
            except Empty:
                pass

            self.__stop_event.wait(0.1)
        return


class LogQueue:
    def __init__(self):
        self.queue = Queue()
        self.__logging = True
        self.__stop_event = threading.Event()

        try:
            self.__log_file = open(os.path.dirname(os.path.realpath(__file__)) + '/PiStation 2.log', 'a')
        except:
            with open('/home/pi/PiStation 2 Error.txt', 'a') as txt:
                txt.write(sys.exc_info()[0])

        threading.Thread(name='LogQueue', target=self.__logger).start()

    def queue_add(self, text):
        self.queue.put_nowait(text)

    def close(self):
        self.queue.join()
        self.__log_file.close()
        self.__logging = False

    def __logger(self):
        while self.__logging:
            try:
                text = self.queue.get()
                self.__log_file.write(text)
                self.__log_file.flush()
                os.fsync(self.__log_file.fileno())
                self.queue.task_done()
            except Empty:
                pass

            self.__stop_event.wait(0.1)
        return


# LED Controller class
# Wrapper for toggling the LED(s)
class LedController:
    def __init__(self, led_pin, led_on=True):
        self.led_pin = led_pin
        self.led_on = led_on

        GPIO.setup(self.led_pin, GPIO.OUT)
        self.set_state(led_on)

    def toggle_led(self):
        self.led_on = not self.led_on
        GPIO.output(self.led_pin, self.led_on)

    def set_state(self, state):
        self.led_on = state
        GPIO.output(self.led_pin, self.led_on)


# rsync Monitor class
# Checks the process list to see if rsync is running
class RsyncMonitor:
    # LedController, delay between flashes
    def __init__(self, led, delay=0.2, log_queue=None, print_queue=None):
        # User can create the class using a pin number or supply
        # a LedController
        self.printer = print_queue
        self.logger = log_queue

        if isinstance(led, int):
            if 40 >= led >= 3:
                led = LedController(led)

        if not isinstance(led, LedController):
            log_text = datetime.strftime(datetime.now(), '[%Y-%m-%d] [%H:%M:%S]') + ' Invalid LedController'
            if self.printer or self.logger:
                if self.printer:
                    self.printer.queue_add(log_text)
                if self.logger:
                    self.logger.queue_add(log_text + '\r\n')
            else:
                print(log_text)

            raise ValueError

        if not (isinstance(delay, int) or isinstance(delay, float)):
            log_text = datetime.strftime(datetime.now(), '[%Y-%m-%d] [%H:%M:%S]') + ' Delay must be int or float'
            if self.printer or self.logger:
                if self.printer:
                    self.printer.queue_add(log_text)
                if self.logger:
                    self.logger.queue_add(log_text + '\r\n')
            else:
                print(log_text)
            raise ValueError

        self.led_controller = led
        self.delay = delay
        self.__flashing = None
        self.__flash_stop = None
        self.__rsync_pid = 0

    # Returns true if rsync is running (copying)
    def is_copying(self):
        if self.__rsync_pid:
            # Saved the last rsync PID, check to see if
            # it still exists
            try:
                os.kill(self.__rsync_pid, 0)
            except OSError:
                # Last PID does not exist, continue
                self.__rsync_pid = 0
                pass
            else:
                # Last PID still exists, still running
                return True
        try:
            # Check to see if rsync exists
            subprocess.check_output(['pidof', 'rsync'])
            # rsync exists, return true
            return True
        # When the process does not exist, subprocess raises a CalledProcessError
        # rsync is not running, return False
        except subprocess.CalledProcessError:
            return False

    # Monitor function, main loop for this class
    def monitor(self, stop_event):
        copy_timer = time()

        try:
            while not stop_event.is_set():
                # If rsync is running (copying)
                if self.is_copying():
                    # Not currently flashing the LED(s)
                    if not self.__flashing:
                        # Timer used to show how long the copying process lasted
                        copy_timer = time()

                        # Create the stop event, thread, and start it (start flashing)
                        self.__flash_stop = threading.Event()
                        self.__flashing = threading.Thread(target=self.__flash,
                                                           args=(self.__flash_stop, self.led_controller, self.delay))
                        self.__flashing.start()

                        if self.printer or self.logger:
                            log_string = datetime.strftime(datetime.now(), '[%Y-%m-%d] [%H:%M:%S]') + ' Copying started'

                            if self.logger:
                                self.logger.queue_add(log_string + '\r\n')

                            if self.printer:
                                self.printer.queue_add(log_string)
                # Currently flashing but rsync is no longer running
                elif self.__flashing:
                    # Stop the thread
                    self.__flash_stop.set()
                    # Clear it
                    self.__flashing = self.__flash_stop = None

                    if self.printer or self.logger:

                        log_string = datetime.strftime(datetime.now(), '[%Y-%m-%d] [%H:%M:%S]') + \
                                     ' Copying ended: ' + self.__timer_to_time(copy_timer)

                        if self.logger:
                            self.logger.queue_add(log_string + '\r\n')

                        if self.printer:
                            self.printer.queue_add(log_string)

                            copy_timer = 0

                    # Slight delay while we wait for the thread to close
                    stop_event.wait(0.1)

                stop_event.wait(0.25)
        # Some error happened, close out of this gracefully
        except Exception as e:
            if hasattr(e, 'message'):
                print(e.message)
            else:
                print(e)
            pass

        if self.__flashing:
            self.__flash_stop.set()
        return

    @staticmethod
    def __timer_to_time(timer):
        seconds = time() - timer
        days = int(seconds / 86400)
        seconds %= 86400
        hours = int(seconds / 3600)
        seconds %= 3600
        return '{0:02d}d {1:02d}h {2:02d}m {3:02d}s'.format(days, hours, int(seconds / 60), int(seconds % 60))

    # Function used for flashing the LED(s)
    # Not inside the main while loop, this is threaded so the flashing
    # is never interrupted from the sleeps
    @staticmethod
    def __flash(stop_event, led, delay):
        led_default_state = led.led_on

        # While the stop event has not been set, keep flashing
        while not stop_event.is_set():
            led.toggle_led()
            stop_event.wait(delay)

        # Put the LED back to the default state we found it in
        led.set_state(led_default_state)


class FanMonitor:
    def __init__(self, gpio_pin_low, gpio_pin_high, temp_fan_low=55, temp_fan_high=65, temp_fan_off=45,
                 min_seconds_on=30, log_queue=None, print_queue=None):
        self.rpi_cpu_freq = '/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq'
        self.fan_state = FAN_OFF
        self.fan_pin_low = gpio_pin_low
        self.fan_pin_high = gpio_pin_high
        self.last_temperature = 0
        self.temp_fan_low = temp_fan_low
        self.temp_fan_high = temp_fan_high
        self.temp_fan_off = temp_fan_off
        self.__fan_timer = 0
        self.min_seconds_on = min_seconds_on
        self.logger = log_queue
        self.printer = print_queue

        GPIO.setup(self.fan_pin_low, GPIO.OUT)
        GPIO.setup(self.fan_pin_high, GPIO.OUT)
        GPIO.output(self.fan_pin_low, False)
        GPIO.output(self.fan_pin_high, False)

    @staticmethod
    def cpu_temp():
        return float(os.popen('vcgencmd measure_temp').readline().replace('temp=', '').replace('\'C\n', ''))

    @staticmethod
    def cpu_percent():
        return float(psutil.cpu_percent(interval=1))

    def cpu_speed(self):
        current_freq = str(subprocess.check_output('cat ' + self.rpi_cpu_freq, shell=True)).replace('0000\n', '')

        return \
            float('0.' + current_freq) \
            if int(current_freq) < 100 else \
            float('{}.{}'.format(current_freq[:1], current_freq[1:]))

    def check_temp(self):
        current_temp = self.cpu_temp()

        if current_temp >= self.temp_fan_low:
            if self.__fan_timer:
                self.__fan_timer = 0

                if self.logger or self.printer:
                    log_write = datetime.strftime(datetime.now(), '[%Y-%m-%d] [%H:%M:%S]') + \
                                ' Resetting timer: CPU Temperature = {}°C | CPU Usage = {}% | CPU Speed = {}GHz' \
                                .format(current_temp, self.cpu_percent(), self.cpu_speed())

                    if self.logger:
                        self.logger.queue_add(log_write + '\r\n')

                    if self.printer:
                        self.printer.queue_add(log_write)

            if current_temp >= self.temp_fan_high:
                if self.fan_state == FAN_HIGH:
                    return

                self.set_state(FAN_HIGH)
                speed = 'high fan speed'
                temp = self.temp_fan_high
            else:
                if self.fan_state == FAN_LOW:
                    return
                self.set_state(FAN_LOW)
                speed = 'low fan speed'
                temp = self.temp_fan_low

            if self.logger or self.printer:
                log_write = datetime.strftime(datetime.now(), '[%Y-%m-%d] [%H:%M:%S]') + \
                            ' Temperature reached for ' + speed + ' ({}°C): ' \
                            'CPU Temperature = {}°C | CPU Usage = {}% | CPU Speed = {}GHz' \
                            .format(temp, current_temp, self.cpu_percent(), self.cpu_speed())

                if self.logger:
                    self.logger.queue_add(log_write + '\r\n')

                if self.printer:
                    self.printer.queue_add(log_write)

        elif current_temp <= self.temp_fan_off and self.fan_state:
            if not self.__fan_timer:
                self.__fan_timer = time()

                if self.logger or self.printer:
                    log_write = datetime.strftime(datetime.now(), '[%Y-%m-%d] [%H:%M:%S]') + \
                                ' Min temp reached ({}°C), Initializing countdown ({}s): ' \
                                'CPU Temperature = {}°C | CPU Usage = {}% | CPU Speed = {}GHz' \
                                .format(self.temp_fan_off, self.min_seconds_on, current_temp, self.cpu_percent(),
                                        self.cpu_speed())

                    if self.logger:
                        self.logger.queue_add(log_write + '\r\n')

                    if self.printer:
                        self.printer.queue_add(log_write)
                return

            current_time = time()

            if self.logger or self.printer:
                log_write = datetime.strftime(datetime.now(), '[%Y-%m-%d] [%H:%M:%S]') + \
                            ' {}s left: CPU Temperature = {}°C | CPU Usage = {}% | CPU Speed = {}GHz' \
                            .format(int(self.min_seconds_on - (current_time - self.__fan_timer)),
                                    current_temp, self.cpu_percent(), self.cpu_speed())
                if self.logger:
                    self.logger.queue_add(log_write + '\r\n')

                if self.printer:
                    self.printer.queue_add(log_write)

            if current_time - self.__fan_timer > self.min_seconds_on:
                self.set_state(False)
                self.__fan_timer = 0
                if self.logger or self.printer:
                    log_write = datetime.strftime(datetime.now(), '[%Y-%m-%d] [%H:%M:%S]') + \
                                ' Min temp and time reached, turning fan off'
                    if self.logger:
                        self.logger.queue_add(log_write + '\r\n')

                    if self.printer:
                        self.printer.queue_add(log_write)

    def toggle_fan(self):
        return self.set_state(not self.fan_state)

    def set_state(self, state):
        if self.fan_state == FAN_HIGH:
            GPIO.output(self.fan_pin_high, False)
        elif self.fan_state == FAN_LOW:
            GPIO.output(self.fan_pin_low, False)

        if state == FAN_HIGH:
            GPIO.output(self.fan_pin_high, True)
        elif state == FAN_LOW:
            GPIO.output(self.fan_pin_low, True)

        self.fan_state = state
        return self.fan_state


def button_pressed(pin):
    if not GPIO.input(pin):
        if logger or printer:
            log_string = datetime.strftime(datetime.now(), '[%Y-%m-%d] [%H:%M:%S]') + ' Reset button pressed ....'
            if logger:
                logger.queue_add(log_string + '\r\n')

            if printer:
                printer.queue_add(log_string)
        timer = time()

        rsync_stop.set()

        while not GPIO.input(pin):
            if time() - timer >= 2:
                if logger or printer:
                    log_string = datetime.strftime(datetime.now(),
                                                   '[%Y-%m-%d] [%H:%M:%S]') + ' Shutting down PiStation 2'
                    if logger:
                        logger.queue_add(log_string + '\r\n')

                    if printer:
                        printer.queue_add(log_string)
                close()
                subprocess.call('shutdown -h now', shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                exit()

            led_controller.toggle_led()
            sleep(0.15)

        if logger or printer:
            log_string = datetime.strftime(datetime.now(), '[%Y-%m-%d] [%H:%M:%S]') + ' Restarting PiStation 2'
            if logger:
                logger.queue_add(log_string + '\r\n')

            if printer:
                printer.queue_add(log_string)

        close()
        subprocess.call('reboot now', shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def close():
    rsync_stop.set()

    try:
        if logger:
            logger.close()
    except:
        pass

    try:
        if printer:
            printer.close()
    except:
        pass

    GPIO.cleanup()

logger = LogQueue()
printer = None # PrintQueue()

# Set the restart and shutdown pin
# Enable the Pull Up resistor, allows us to turn the pi back on pressing
# the reset/power button
GPIO.setup(restart_shutdown_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

GPIO.add_event_detect(restart_shutdown_pin, GPIO.BOTH, callback=button_pressed)

rsync_stop = threading.Event()
led_controller = LedController(front_led_pin)
fan_monitor = FanMonitor(fan_pin_low, fan_pin_high, log_queue=logger)
rsync_monitor = RsyncMonitor(led_controller, log_queue=logger)
rsync_thread = threading.Thread(target=rsync_monitor.monitor, args=(rsync_stop,))
rsync_thread.start()

try:
    while True:
        sleep(5)
        fan_monitor.check_temp()

except KeyboardInterrupt:
    print(datetime.strftime(datetime.now(), '[%Y-%m-%d] [%H:%M:%S]') + ' Keyboard interrupt')
    close()

sys.exit()
