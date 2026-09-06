# Task
We are setting up for a fNIRS recording experimente, see the protocol in the
folder.

To this end we are both creating the fNIRS motnage + 
we are creating the lsl-connected pythons script to accuratly mark the data. 
See dev/cube-nirs for example how to create a proper triggering script, then
create it based on the protocol. 

If not noted in the protocol, we again use a 1khz audio cuo to tell the subject
the next block is onset.

In ~/nirs/configurations I have a examples of actually both the raw
NIRSSIte-produced montage .probeinfo etc, but also acutally Aurora compatible montages. 
See the protocol, and are able to actually directly code / write our own montage
files instead of me using NIRSSiste, that would be awesome.

Lets push all to lydia-adept.git and make it public so I can gather all we
produce on the actual acquistion pc (which is running Windows 11 )
