# -*- coding: utf-8 -*-
import xbmc
import xbmcgui

import helper.utils
import helper.loghandler

ACTION_PARENT_DIR = 9
ACTION_PREVIOUS_MENU = 10
ACTION_BACK = 92
ACTION_SELECT_ITEM = 7
ACTION_MOUSE_LEFT_CLICK = 100
USER_IMAGE = 150
LIST = 155
CANCEL = 201
MESSAGE_BOX = 202
MESSAGE = 203
BUSY = 204
EMBY_CONNECT = 205
MANUAL_SERVER = 206

class ServerConnect(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        self.user_image = None
        self.servers = []
        self.Utils = helper.utils.Utils()
        self._selected_server = None
        self._connect_login = False
        self._manual_server = False
        self.message = None
        self.message_box = None
        self.busy = None
        self.list_ = None
        self.LOG = helper.loghandler.LOG('EMBY.dialogs.serverconnect.ServerConnect')
        xbmcgui.WindowXMLDialog.__init__(self, *args, **kwargs)

    #connect_manager, user_image, servers, emby_connect
    def set_args(self, **kwargs):
        for key, value in list(kwargs.items()):
            setattr(self, key, value)

    def is_server_selected(self):
        return bool(self._selected_server)

    def get_server(self):
        return self._selected_server

    def is_connect_login(self):
        return self._connect_login

    def is_manual_server(self):
        return self._manual_server

    def onInit(self):
        self.message = self.getControl(MESSAGE)
        self.message_box = self.getControl(MESSAGE_BOX)
        self.busy = self.getControl(BUSY)
        self.list_ = self.getControl(LIST)

        for server in self.servers:
            server_type = "wifi" if server.get('ExchangeToken') else "network"
            self.list_.addItem(self._add_listitem(server['Name'], server['Id'], server_type))

        if self.user_image is not None:
            self.getControl(USER_IMAGE).setImage(self.user_image)

        if not self.emby_connect: # Change connect user
            self.getControl(EMBY_CONNECT).setLabel("[B]%s[/B]" % self.Utils.Translate(30618))

        if self.servers:
            self.setFocus(self.list_)

    def _add_listitem(self, label, server_id, server_type):
        item = xbmcgui.ListItem(label)
        item.setProperty('id', server_id)
        item.setProperty('server_type', server_type)
        return item

    def onAction(self, action):
        if action in (ACTION_BACK, ACTION_PREVIOUS_MENU, ACTION_PARENT_DIR):
            self.close()

        if action in (ACTION_SELECT_ITEM, ACTION_MOUSE_LEFT_CLICK):
            if self.getFocusId() == LIST:
                server = self.list_.getSelectedItem()
                self.LOG.info('Server Id selected: %s' % server.getProperty('id'))

                if self._connect_server():
                    self.message_box.setVisibleCondition('false')
                    self.close()

    def onClick(self, control):
        if control == EMBY_CONNECT:
            self.connect_manager.clear_data()
            self._connect_login = True
            self.close()
        elif control == MANUAL_SERVER:
            self._manual_server = True
            self.close()
        elif control == CANCEL:
            self.close()

    def _connect_server(self):
        server = self.connect_manager.get_server_info()
        self.message.setLabel("%s %s..." % (self.Utils.Translate(30610), server['Name']))
        self.message_box.setVisibleCondition('true')
        self.busy.setVisibleCondition('true')
        result = self.connect_manager.connect_to_server(server, {})

        if result['State'] == 0: #Unavailable
            self.busy.setVisibleCondition('false')
            self.message.setLabel(self.Utils.Translate(30609))
            return False

        xbmc.sleep(1000)
        self._selected_server = result['Servers'][0]
        return True