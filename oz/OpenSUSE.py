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
OpenSUSE installation
"""

import re
import shutil
import os
import libxml2

import oz.Guest
import oz.ozutil
import oz.OzException

class OpenSUSEGuest(oz.Guest.CDGuest):
    """
    Class for OpenSUSE installation.
    """
    def __init__(self, tdl, config, auto):
        oz.Guest.CDGuest.__init__(self, tdl, "virtio", None, None, "virtio",
                                  config)

        self.autoyast = auto
        if self.autoyast is None:
            self.autoyast = oz.ozutil.generate_full_auto_path("opensuse-" + self.tdl.update + "-jeos.xml")

        self.url = self._check_url(self.tdl, iso=True, url=False)

        self.sshprivkey = os.path.join('/etc', 'oz', 'id_rsa-icicle-gen')

    def _modify_iso(self):
        """
        Method to make the boot ISO auto-boot with appropriate parameters.
        """
        self.log.debug("Putting the autoyast in place")

        outname = os.path.join(self.iso_contents, "autoinst.xml")

        if self.autoyast == oz.ozutil.generate_full_auto_path("opensuse-" + self.tdl.update + "-jeos.xml"):
            doc = libxml2.parseFile(self.autoyast)

            xp = doc.xpathNewContext()
            xp.xpathRegisterNs("suse", "http://www.suse.com/1.0/yast2ns")

            pw = xp.xpathEval('/suse:profile/suse:users/suse:user/suse:user_password')
            pw[0].setContent(self.rootpw)

            doc.saveFile(outname)
        else:
            shutil.copy(self.autoyast, outname)

        self.log.debug("Modifying the boot options")
        isolinux_cfg = os.path.join(self.iso_contents, "boot", self.tdl.arch,
                                    "loader", "isolinux.cfg")
        f = open(isolinux_cfg, "r")
        lines = f.readlines()
        f.close()
        for index, line in enumerate(lines):
            if re.match("timeout", line):
                lines[index] = "timeout 1\n"
            elif re.match("default", line):
                lines[index] = "default customiso\n"
        lines.append("label customiso\n")
        lines.append("  kernel linux\n")
        lines.append("  append initrd=initrd splash=silent instmode=cd autoyast=default")

        f = open(isolinux_cfg, "w")
        f.writelines(lines)
        f.close()

    def _generate_new_iso(self):
        """
        Method to create a new ISO based on the modified CD/DVD.
        """
        self.log.info("Generating new ISO")
        oz.Guest.subprocess_check_output(["mkisofs", "-r", "-J", "-V", "Custom",
                                          "-b", "boot/" + self.tdl.arch + "/loader/isolinux.bin",
                                          "-c", "boot/" + self.tdl.arch + "/loader/boot.cat",
                                          "-no-emul-boot",
                                          "-boot-load-size", "4",
                                          "-boot-info-table", "-graft-points",
                                          "-iso-level", "4", "-pad",
                                          "-allow-leading-dots", "-l",
                                          "-o", self.output_iso,
                                          self.iso_contents])

    def generate_install_media(self, force_download=False):
        """
        Method to generate the install media for OpenSUSE operating
        systems.  If force_download is False (the default), then the
        original media will only be fetched if it is not cached locally.  If
        force_download is True, then the original media will be downloaded
        regardless of whether it is cached locally.
        """
        return self._iso_generate_install_media(self.url, force_download)

    def install(self, timeout=None, force=False):
        """
        Method to run the operating system installation.
        """
        return self._do_install(timeout, force, 1)

    def _shutdown_guest(self, guestaddr, libvirt_dom):
        """
        Method to shutdown the guest (gracefully at first, then with prejudice).
        """
        if guestaddr is not None:
            try:
                self.guest_execute_command(guestaddr, 'shutdown -h now')
                if not self._wait_for_guest_shutdown(libvirt_dom):
                    self.log.warn("Guest did not shutdown in time, going to kill")
                else:
                    libvirt_dom = None
            except:
                self.log.warn("Failed shutting down guest, forcibly killing")

        if libvirt_dom is not None:
            libvirt_dom.destroy()

    def guest_execute_command(self, guestaddr, command, timeout=10):
        """
        Method to execute a command on the guest and return the output.
        """
        # ServerAliveInterval protects against NAT firewall timeouts
        # on long-running commands with no output
        # PasswordAuthentication=no prevents us from falling back to
        # keyboard-interactive password prompting
        return oz.Guest.subprocess_check_output(["ssh", "-i", self.sshprivkey,
                                                 "-o", "ServerAliveInterval=30",
                                                 "-o", "StrictHostKeyChecking=no",
                                                 "-o", "ConnectTimeout=" + str(timeout),
                                                 "-o", "UserKnownHostsFile=/dev/null",
                                                 "-o", "PasswordAuthentication=no",
                                                 "root@" + guestaddr, command])

    def _image_ssh_teardown_step_1(self, g_handle):
        """
        First step to undo __image_ssh_setup (remove authorized keys).
        """
        self.log.debug("Teardown step 1")
        # reset the authorized keys
        self.log.debug("Resetting authorized_keys")
        if g_handle.exists('/root/.ssh/authorized_keys'):
            g_handle.rm('/root/.ssh/authorized_keys')
        if g_handle.exists('/root/.ssh/authorized_keys.icicle'):
            g_handle.mv('/root/.ssh/authorized_keys.icicle',
                        '/root/.ssh/authorized_keys')

    def _image_ssh_teardown_step_2(self, g_handle):
        """
        Second step to undo __image_ssh_setup (remove custom sshd_config).
        """
        self.log.debug("Teardown step 2")
        # remove custom sshd_config
        self.log.debug("Resetting sshd_config")
        if g_handle.exists('/etc/ssh/sshd_config'):
            g_handle.rm('/etc/ssh/sshd_config')
        if g_handle.exists('/etc/ssh/sshd_config.icicle'):
            g_handle.mv('/etc/ssh/sshd_config.icicle', '/etc/ssh/sshd_config')

        # reset the service link
        self.log.debug("Resetting sshd service")
        if g_handle.exists("/etc/init.d/after.local"):
            g_handle.rm("/etc/init.d/after.local")
        if g_handle.exists("/etc/init.d/after.local.icicle"):
            g_handle.mv("/etc/init.d/after.local.icicle",
                        "/etc/init.d/after.local")

    def _image_ssh_teardown_step_3(self, g_handle):
        """
        Third step to undo __image_ssh_setup (remove guest announcement).
        """
        self.log.debug("Teardown step 3")
        # remove announce cronjob
        self.log.debug("Resetting announcement to host")
        if g_handle.exists('/etc/cron.d/announce'):
            g_handle.rm('/etc/cron.d/announce')

        # remove icicle-nc binary
        self.log.debug("Removing icicle-nc binary")
        if g_handle.exists('/root/icicle-nc'):
            g_handle.rm('/root/icicle-nc')

        # reset the service link
        self.log.debug("Resetting cron service")
        runlevel = self._get_default_runlevel(g_handle)
        startuplink = '/etc/rc.d/rc' + runlevel + ".d/S06cron"
        if g_handle.exists(startuplink):
            g_handle.rm(startuplink)
        if g_handle.exists(startuplink + ".icicle"):
            g_handle.mv(startuplink + ".icicle", startuplink)

    def _collect_teardown(self, libvirt_xml):
        """
        Method to reverse the changes done in __collect_setup.
        """
        self.log.info("Collection Teardown")

        g_handle = self._guestfs_handle_setup(libvirt_xml)

        try:
            self._image_ssh_teardown_step_1(g_handle)

            self._image_ssh_teardown_step_2(g_handle)

            self._image_ssh_teardown_step_3(g_handle)
        finally:
            self._guestfs_handle_cleanup(g_handle)
            shutil.rmtree(self.icicle_tmp)

    def _do_icicle(self, guestaddr):
        """
        Method to collect the package information and generate the ICICLE XML.
        """
        stdout, stderr, retcode = self.guest_execute_command(guestaddr,
                                                             'rpm -qa')

        return self._output_icicle_xml(stdout.split("\n"),
                                       self.tdl.description)

    def generate_icicle(self, libvirt_xml):
        """
        Method to generate the ICICLE from an operating system after
        installation.  The ICICLE contains information about packages and
        other configuration on the diskimage.
        """
        self.log.info("Generating ICICLE")

        self._collect_setup(libvirt_xml)

        icicle_output = ''
        libvirt_dom = None
        try:
            libvirt_dom = self.libvirt_conn.createXML(libvirt_xml, 0)

            try:
                guestaddr = None
                guestaddr = self._wait_for_guest_boot(libvirt_dom)
                icicle_output = self._do_icicle(guestaddr)
            finally:
                self._shutdown_guest(guestaddr, libvirt_dom)

        finally:
            self._collect_teardown(libvirt_xml)

        return icicle_output

    def _get_default_runlevel(self, g_handle):
        """
        Method to determine the default runlevel based on the /etc/inittab.
        """
        runlevel = "3"
        if g_handle.exists('/etc/inittab'):
            lines = g_handle.cat('/etc/inittab').split("\n")
            for line in lines:
                if re.match('id:', line):
                    try:
                        runlevel = line.split(':')[1]
                    except:
                        pass
                    break

        return runlevel

    def _image_ssh_setup_step_1(self, g_handle):
        """
        First step for allowing remote access (generate and upload ssh keys).
        """
        # part 1; upload the keys
        self.log.debug("Step 1: Uploading ssh keys")
        if not g_handle.exists('/root/.ssh'):
            g_handle.mkdir('/root/.ssh')

        if g_handle.exists('/root/.ssh/authorized_keys'):
            g_handle.mv('/root/.ssh/authorized_keys',
                        '/root/.ssh/authorized_keys.icicle')

        self._generate_openssh_key(self.sshprivkey)

        g_handle.upload(self.sshprivkey + ".pub", '/root/.ssh/authorized_keys')

    def _image_ssh_setup_step_2(self, g_handle):
        """
        Second step for allowing remote access (ensure sshd is running).
        """
        # part 2; check and setup sshd
        self.log.debug("Step 2: setup sshd")
        if not g_handle.exists('/etc/init.d/sshd') or not g_handle.exists('/usr/sbin/sshd'):
            raise oz.OzException.OzException("ssh not installed on the image, cannot continue")

        if g_handle.exists("/etc/init.d/after.local"):
            g_handle.mv("/etc/init.d/after.local",
                        "/etc/init.d/after.local.icicle")

        local = self.icicle_tmp + "/after.local"
        f = open(local, "w")
        f.write("/sbin/service sshd start\n")
        f.close()

        g_handle.upload(local, "/etc/init.d/after.local")
        os.unlink(local)

        sshd_config = \
"""PasswordAuthentication no
UsePAM yes

X11Forwarding yes

Subsystem	sftp	/usr/lib64/ssh/sftp-server

AcceptEnv LANG LC_CTYPE LC_NUMERIC LC_TIME LC_COLLATE LC_MONETARY LC_MESSAGES
AcceptEnv LC_PAPER LC_NAME LC_ADDRESS LC_TELEPHONE LC_MEASUREMENT
AcceptEnv LC_IDENTIFICATION LC_ALL
"""
        sshd_config_file = self.icicle_tmp + "/sshd_config"
        f = open(sshd_config_file, 'w')
        f.write(sshd_config)
        f.close()

        if g_handle.exists('/etc/ssh/sshd_config'):
            g_handle.mv('/etc/ssh/sshd_config', '/etc/ssh/sshd_config.icicle')
        g_handle.upload(sshd_config_file, '/etc/ssh/sshd_config')
        os.unlink(sshd_config_file)

    def _image_ssh_setup_step_3(self, g_handle):
        """
        Third step for allowing remote access (make the guest announce itself
        on bootup).
        """
        # part 3; make sure the guest announces itself
        self.log.debug("Step 3: Guest announcement")
        if not g_handle.exists('/etc/init.d/cron') or not g_handle.exists('/usr/sbin/cron'):
            raise oz.OzException.OzException("cron not installed on the image, cannot continue")

        iciclepath = oz.ozutil.generate_full_guesttools_path('icicle-nc')
        g_handle.upload(iciclepath, '/root/icicle-nc')
        g_handle.chmod(0755, '/root/icicle-nc')

        announcefile = self.icicle_tmp + "/announce"
        f = open(announcefile, 'w')
        f.write('*/1 * * * * root /bin/bash -c "/root/icicle-nc ' + self.host_bridge_ip + ' ' + str(self.listen_port) + ' ' + str(self.uuid) + '"\n')
        f.close()

        g_handle.upload(announcefile, '/etc/cron.d/announce')

        runlevel = self._get_default_runlevel(g_handle)
        startuplink = '/etc/rc.d/rc' + runlevel + ".d/S06cron"
        if g_handle.exists(startuplink):
            g_handle.mv(startuplink, startuplink + ".icicle")
        g_handle.ln_sf('/etc/init.d/cron', startuplink)

        os.unlink(announcefile)

    def _collect_setup(self, libvirt_xml):
        """
        Setup the guest for remote access.
        """
        self.log.info("Collection Setup")

        self.mkdir_p(self.icicle_tmp)

        g_handle = self._guestfs_handle_setup(libvirt_xml)

        # we have to do 3 things to make sure we can ssh into OpenSUSE:
        # 1)  Upload our ssh key
        # 2)  Make sure sshd is running on boot
        # 3)  Make the guest announce itself to the host

        try:
            try:
                self._image_ssh_setup_step_1(g_handle)

                try:
                    self._image_ssh_setup_step_2(g_handle)

                    try:
                        self._image_ssh_setup_step_3(g_handle)
                    except:
                        self._image_ssh_teardown_step_3(g_handle)
                        raise
                except:
                    self._image_ssh_teardown_step_2(g_handle)
                    raise
            except:
                self._image_ssh_teardown_step_1(g_handle)
                raise

        finally:
            self._guestfs_handle_cleanup(g_handle)

    def _customize_repos(self, guestaddr):
        """
        Method to add user-provided repositories to the guest.
        """
        self.log.debug("Installing additional repository files")
        for repo in self.tdl.repositories.values():
            self.guest_execute_command(guestaddr,
                                       "zypper addrepo %s %s" % (repo.url,
                                                                 repo.name))

    def _do_customize(self, guestaddr):
        """
        Method to customize by installing additional packages and files.
        """
        self._customize_repos(guestaddr)

        self.log.debug("Installing custom packages")
        packstr = ''
        for package in self.tdl.packages:
            packstr += package.name + ' '

        if packstr != '':
            # due to a bug in OpenSUSE 11.1, we want to remove the default
            # CD repo first
            stdout, stderr, retcode = self.guest_execute_command(guestaddr,
                                                                 'zypper repos -d')
            removerepos = []
            for line in stdout.split('\n'):
                if re.match("^[0-9]+", line):
                    split = line.split('|')

                    if re.match("^cd://", split[7].strip()):
                        removerepos.append(split[0].strip())
            for repo in removerepos:
                self.guest_execute_command(guestaddr,
                                           'zypper removerepo %s' % (repo))

            self.guest_execute_command(guestaddr,
                                       'zypper -n install %s' % (packstr))

        self.log.debug("Syncing")
        self.guest_execute_command(guestaddr, 'sync')

    def customize(self, libvirt_xml):
        """
        Method to customize the operating system after installation.
        """
        self.log.info("Customizing image")

        if not self.tdl.packages and not self.tdl.files:
            self.log.info("No additional packages or files to install, skipping customization")
            return

        self._collect_setup(libvirt_xml)

        libvirt_dom = None
        try:
            libvirt_dom = self.libvirt_conn.createXML(libvirt_xml, 0)

            try:
                guestaddr = None
                guestaddr = self._wait_for_guest_boot(libvirt_dom)

                self._do_customize(guestaddr)
            finally:
                self._shutdown_guest(guestaddr, libvirt_dom)
        finally:
            self._collect_teardown(libvirt_xml)

    def customize_and_generate_icicle(self, libvirt_xml):
        """
        Method to customize and generate the ICICLE for an operating system
        after installation.  This is equivalent to calling customize() and
        generate_icicle() back-to-back, but is faster.
        """
        self.log.info("Customizing and generating ICICLE")

        self._collect_setup(libvirt_xml)

        libvirt_dom = None
        try:
            libvirt_dom = self.libvirt_conn.createXML(libvirt_xml, 0)

            try:
                guestaddr = None
                guestaddr = self._wait_for_guest_boot(libvirt_dom)

                if self.tdl.packages or self.tdl.files:
                    self._do_customize(guestaddr)

                icicle = self._do_icicle(guestaddr)
            finally:
                self._shutdown_guest(guestaddr, libvirt_dom)
        finally:
            self._collect_teardown(libvirt_xml)

        return icicle

def get_class(tdl, config, auto):
    """
    Factory method for OpenSUSE installs.
    """
    if tdl.update in ["11.0", "11.1", "11.2", "11.3", "11.4"]:
        return OpenSUSEGuest(tdl, config, auto)
