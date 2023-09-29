#!/bin/bash
cd $2
TMPFILE=`mktemp` || exit 1
sum=`openssl dgst -sha1 mets.xml | awk -F '= ' '{print $NF}'`
echo ./mets.xml:sha1:$sum > $TMPFILE
openssl smime -sign -signer $1 -in $TMPFILE > signature.sig
rm $TMPFILE
