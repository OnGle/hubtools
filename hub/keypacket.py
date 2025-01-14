#
# Copyright (c) 2010-2013 Liraz Siri <liraz@turnkeylinux.org>
#
# This file is part of TKLBAM (TurnKey GNU/Linux BAckup and Migration).
#
# TKLBAM is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of
# the License, or (at your option) any later version.
#
import os
import hashlib
import base64
import struct

from Crypto.Cipher import AES

KEY_VERSION = 1

SALT_LEN = 4
KILO_REPEATS_HASH = 80
KILO_REPEATS_CIPHER = 80

FINGERPRINT_LEN = 6

class Error(Exception):
    pass

def _pad(s):
    padded_len = ((len(s) + 2 - 1) |  0xF) + 1
    padding_len = padded_len - len(s) - 2
    return os.urandom(padding_len) + s + struct.pack("!H", len(s))

def _unpad(padded):
    length, = struct.unpack("!H", padded[-2:])
    return padded[-(2 + length) :-2]

def _repeat(f, input, count):
    for x in range(count):
        input = f(input)
    return input

def _cipher_key(passphrase, repeats):
    cipher_key = _repeat(lambda k: hashlib.sha256(k).digest(),
                         passphrase, repeats)
    return cipher_key

def _cipher(cipher_key):
    return AES.new(cipher_key, mode=AES.MODE_CBC, IV='\0' * 16)

def fmt(secret, passphrase):
    salt = os.urandom(SALT_LEN)

    if not passphrase:
        hash_repeats = cipher_repeats = 1
    else:
        hash_repeats = KILO_REPEATS_HASH * 1000 + 1
        cipher_repeats = KILO_REPEATS_CIPHER * 1000 + 1

    cipher_key = _cipher_key(passphrase, hash_repeats)
    plaintext = salt + hashlib.sha1(secret).digest() + secret

    ciphertext = _repeat(lambda v: _cipher(cipher_key).encrypt(v),
                         _pad(plaintext), cipher_repeats)

    fingerprint = hashlib.sha1(secret).digest()[:FINGERPRINT_LEN]
    packet = struct.pack("!BHH", KEY_VERSION,
                         hash_repeats / 1000,
                         cipher_repeats / 1000) + fingerprint + ciphertext

    return base64.b64encode(packet)

def _parse(packet):
    try:
        packet = base64.b64decode(packet)
        version, khr, kcr = struct.unpack("!BHH", packet[:5])
    except (TypeError, struct.error) as e:
        raise Error("can't parse key packet: " + str(e)) from e

    minimum_len = (5 + FINGERPRINT_LEN + 16)
    if len(packet) < minimum_len:
        raise Error("key packet length (%d) smaller than minimum (%d)" % (len(packet), minimum_len))

    if version != KEY_VERSION:
        raise Error("unknown key version (%d)" % version)

    fingerprint = packet[5:5 + FINGERPRINT_LEN]
    ciphertext = packet[5 + FINGERPRINT_LEN:]

    return khr, kcr, fingerprint, ciphertext

def parse(packet, passphrase):
    khr, kcr, _, ciphertext = _parse(packet)

    if not passphrase:
        hash_repeats = cipher_repeats = 1
    else:
        hash_repeats = khr * 1000 + 1
        cipher_repeats = kcr * 1000 + 1

    cipher_key = _cipher_key(passphrase, hash_repeats)
    decrypted = _repeat(lambda v: _cipher(cipher_key).decrypt(v),
                        ciphertext,
                        cipher_repeats)

    decrypted = _unpad(decrypted)

    digest = decrypted[SALT_LEN:SALT_LEN+20]
    secret = decrypted[SALT_LEN+20:]

    if digest != hashlib.sha1(secret).digest():
        raise Error("error decrypting key")

    return secret

def fingerprint(packet):
    return base64.b16encode(_parse(packet)[2])
