#  Gnome15 - Suite of tools for the Logitech G series keyboards and headsets
#  Copyright (C) 2010 Brett Smith <tanktarta@blueyonder.co.uk>
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging
import threading
import time

from keys import (Data, Key)
from runnable import Runnable

logger = logging.getLogger(__name__)


class InputProcessor(object):
    """Object to process key presses."""

    @staticmethod
    def process_input(inputEvent):
        """Processes given event.

        Should return as fast as possible.  Any time-consuming processing
        should be done in another thread.

        @param inputEvent Event to process.
        @return True if event was consumed, or False if ignored.

        """
        return False


class InputEvent(object):
    """Event created by a key press or release."""

    def __init__(self, oldState, newState, keysDown, keysUp):
        """Creates an InputEvent.

        @param oldState State before event happened.
        @param newState State after event happened.
        @param keysDown Keys newly pressed.
        @param keysUp Kys released by this event.

        """
        self.oldState = oldState
        self.newState = newState
        self.keysDown = keysDown
        self.keysUp = keysUp


class State(object):
    """Current state of keyboard."""

    def __init__(self):
        self.__keysDown = set()

    @staticmethod
    def _data_to_keys_g_and_m(data):
        """Converts a G/M keys data package to a set of keys defined as
        pressed by it.

        """
        if len(data) != 4 or data[0] != 2:
            raise ValueError("not a multimedia key packet: " + str(data))
        empty = 0x400000
        cur_val = data[3] << 16 | data[2] << 8 | data[1]
        keys = []
        while cur_val != empty:
            found_a_key = False
            for val in Data.gmKeys.keys():
                if val & cur_val == val:
                    cur_val ^= val
                    keys.append(Data.gmKeys[val])
                    found_a_key = True
            if not found_a_key:
                raise ValueError("incorrect g/m key packet: " +
                                 str(data))

        return set(keys)
        # self.__keysDown = set()

    @staticmethod
    def _data_to_keys_d(data):
        """Converts a D data package to a set of keys defined as
        pressed by it.
        """
        if len(data) != 2 or data[1] != 0x80:
            raise ValueError("not a D key packet: " + str(data))
        cur_val = data[0]
        keys = []

        '''Zero is release
        '''
        if cur_val != 0:
            found_a_key = False
            for val in Data.displayKeys.keys():
                if val & cur_val == val:
                    cur_val ^= val
                    keys.append(Data.displayKeys[val])
                    found_a_key = True
            if not found_a_key:
                raise ValueError("incorrect D key packet: " +
                                 str(data))
        return set(keys)

    @staticmethod
    def _data_to_keys_mm(data):
        """Converts a multimedia keys data package to a set of keys defined as
        pressed by it.

        """
        if len(data) != 2 or data[0] not in [1, 3]:
            raise ValueError("not a multimedia key packet: " + str(data))
        if data[0] == 1:
            cur_val = data[1]
            keys = []
            while cur_val:
                found_a_key = False
                for val in Data.mmKeys.keys():
                    if val & cur_val == val:
                        cur_val ^= val
                        keys.append(Data.mmKeys[val])
                        found_a_key = True
                if not found_a_key:
                    raise ValueError("incorrect multimedia key packet: " +
                                     str(data))
        elif data == [3, 1]:
            keys = [Key.WINKEY_SWITCH]
        elif data == [3, 0]:
            keys = []
        else:
            raise ValueError("incorrect multimedia key packet: " + str(data))

        return set(keys)

    def _update_keys_down(self, possibleKeys, keys):
        """Updates internal keysDown set.

        Updates the current state of all keys in 'possibleKeys' with state
        given in 'keys'.

        Example:
        Currently set as pressed in self.__keysDown: [A, B]
        possibleKeys: [B, C, D]
        keys: [C]

        This would set self.__keysDown to [A, C] and return ([C], [B])

        @param possibleKeys Keys whose state could be given as 'pressed' at the
        same time by 'keys'.
        @param keys Current state of all keys in possibleKeys.
        @return A pair of sets listing newly pressed and newly released keys.

        """
        keys_down = set()
        keys_up = set()
        for key in possibleKeys:
            if key in keys:
                if key not in self.__keysDown:
                    self.__keysDown.add(key)
                    keys_down.add(key)
            else:
                if key in self.__keysDown:
                    self.__keysDown.remove(key)
                    keys_up.add(key)
        return keys_down, keys_up

    def clone(self):
        """Returns an exact copy of this state."""
        state = State()
        state.__keysDown = set(self.__keysDown)
        return state

    def packet_received_g_and_m(self, data):
        """Mutates the state by given data packet from G- and M- keys.

        @param data Data packet received.
        @return InputEvent for data packet, or None if data packet was ignored.

        """
        old_state = self.clone()
        evt = None
        logger.debug("G key of %d", len(data))
        if len(data) == 4:
            keys = self._data_to_keys_g_and_m(data)
            keys_down, keys_up = self._update_keys_down(Key.gmKeys, keys)
            new_state = self.clone()
            evt = InputEvent(old_state, new_state, keys_down, keys_up)
        return evt

    def packet_received_d(self, data):
        """Mutates the state by given data packet from D- keys.

        @param data Data packet received.
        @return InputEvent for data packet, or None if data packet was ignored.

        """
        old_state = self.clone()
        evt = None
        logger.debug("D key of %d", len(data))
        if len(data) == 2:
            keys = self._data_to_keys_d(data)
            keys_down, keys_up = self._update_keys_down(Key.displayKeys, keys)
            new_state = self.clone()
            evt = InputEvent(old_state, new_state, keys_down, keys_up)
        return evt

    def packet_received_mm(self, data):
        """Mutates the state by given data packet from multimedia keys.

        @param data Data packet received.
        @return InputEvent for data packet.

        """
        old_state = self.clone()
        if len(data) != 2:
            raise ValueError("incorrect multimedia key packet: " + str(data))
        logger.debug("MM or Win key of %d", len(data))
        keys = self._data_to_keys_mm(data)
        win_key_set = {Key.WINKEY_SWITCH}
        if data[0] == 1:
            # update state of all mm keys
            logger.debug("MM key %d", len(data))
            possible_keys = Key.mmKeys.difference(win_key_set)
            keys_down, keys_up = self._update_keys_down(possible_keys, keys)
        else:
            # update winkey state
            logger.debug("Win key")
            keys_down, keys_up = self._update_keys_down(win_key_set, keys)
        new_state = self.clone()
        return InputEvent(old_state, new_state, keys_down, keys_up)


class G19Receiver(Runnable):
    """This receiver consumes all data sent by special keys."""

    def __init__(self, g19):
        Runnable.__init__(self)
        self.__g19 = g19
        self.__ips = []
        self.__mutex = threading.Lock()
        self.__state = State()

    def add_input_processor(self, processor):
        """Adds an input processor."""
        self.__mutex.acquire()
        self.__ips.append(processor)
        self.__mutex.release()
        pass

    def execute(self):
        got_data = False
        processors = self.list_all_input_processors()

        if self.__g19.enable_mm_keys:
            data = self.__g19.read_multimedia_keys()
            if data:
                logger.debug('MM keys data %s', len(data))
                evt = self.__state.packet_received_mm(data)
                if evt:
                    for proc in processors:
                        if proc.process_input(evt):
                            break
                else:
                    logger.info('MM keys ignored')
                got_data = True

        data = self.__g19.read_g_and_m_keys()
        if data:
            logger.debug('G/M keys data %s', len(data))
            evt = self.__state.packet_received_g_and_m(data)
            if evt:
                for proc in processors:
                    if proc.process_input(evt):
                        break
            else:
                logger.info('G/M keys ignored')
            got_data = True

        data = self.__g19.read_display_menu_keys()
        if data:
            logger.debug('Menu keys Data %s', len(data))
            evt = self.__state.packet_received_d(data)
            if evt:
                for proc in processors:
                    if proc.process_input(evt):
                        break
            else:
                logger.info('Menu keys ignored')
            got_data = True

        if not got_data:
            time.sleep(0.05)

    def list_all_input_processors(self):
        """Returns a list of all input processors currently registered to this
        receiver.

        @return All registered processors.  This list is a copy of the internal
        one.

        """
        self.__mutex.acquire()
        all_processors = list(self.__ips)
        self.__mutex.release()
        return all_processors
