# Copyright (C) 2010,2011  Chris Lalancette <clalance@redhat.com>

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation;
# version 2.1 of the License.

# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA

"""
RHEL-3 installation
"""

import re

import oz.ozutil
import oz.RedHat
import oz.OzException

class RHEL3Guest(oz.RedHat.RedHatCDGuest):
    """
    Class for RHEL-3 installation.
    """
    def __init__(self, tdl, config, auto):
        iso_support = True
        if tdl.distro == "RHEL-3":
            iso_support = False

        oz.RedHat.RedHatCDGuest.__init__(self, tdl, 'rtl8139', None, config,
                                         iso_support, True)

        self.auto = auto

        # override the sshd_config value set in RedHatCDGuest.__init__
        self.sshd_config = \
"""SyslogFacility AUTHPRIV
PasswordAuthentication yes
ChallengeResponseAuthentication no
X11Forwarding yes
Subsystem	sftp	/usr/libexec/openssh/sftp-server
"""

    def _modify_iso(self):
        """
        Method to make the boot ISO auto-boot with appropriate parameters.
        """
        self._copy_kickstart(self.auto, "rhel-3-jeos.ks")

        initrdline = "  append initrd=initrd.img ks=cdrom:/ks.cfg method="
        if self.tdl.installtype == "url":
            initrdline += self.url + "\n"
        else:
            initrdline += "cdrom:/dev/cdrom\n"
        self._modify_isolinux(initrdline)

    def _check_pvd(self):
        """
        Method to ensure the the boot ISO for an ISO install is a DVD
        """
        pvd = self._get_primary_volume_descriptor(self.orig_iso)

        if pvd.system_identifier != "LINUX                           ":
            raise oz.OzException.OzException("Invalid system identifier on ISO for " + self.tdl.distro + " install")

        if self.tdl.distro == "RHEL-3":
            if self.tdl.installtype == "iso":
                raise oz.OzException.OzException("BUG: shouldn't be able to reach RHEL-3 with ISO checking")
            # The boot ISOs for RHEL-3 don't have a whole lot of identifying
            # information.  We just pass through here, doing nothing
        else:
            if self.tdl.installtype == "iso":
                if not re.match("CentOS-3(\.[0-9])? " + self.tdl.arch + " DVD$",
                                pvd.volume_identifier):
                    raise oz.OzException.OzException("Only DVDs are supported for CentOS-3 ISO installs")
            # The boot ISOs for CentOS-3 don't have a whole lot of identifying
            # information.  We just pass through here, doing nothing

def get_class(tdl, config, auto):
    """
    Factory method for RHEL-3 installs.
    """
    if tdl.update in ["GOLD", "U1", "U2", "U3", "U4", "U5", "U6", "U7", "U8", "U9"]:
        return RHEL3Guest(tdl, config, auto)
