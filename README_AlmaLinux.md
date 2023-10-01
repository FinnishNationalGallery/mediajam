# AlmaLinux 9 and dpres-siptools dependencies

MediaJam needs dpres-siptools to be installed with certain dependencies in AlmaLinux 9 server. 
https://github.com/Digital-Preservation-Finland/dpres-siptools

These guidelines are found by testing different combinations and solving error messages. 

> Digital-Preservation-Finland is developing RPM packages to make installation easier. Until then, these instructions is all there is.

Install these as root user.

**FOR PACKAGING IMAGE FILES**
```
dnf install epel-release
dnf install ImageMagick ImageMagick-devel
dnf install perl-Image-ExifTool
```
**FOR PACKAGING VIDEO FILES**
```
dnf install mediainfo-gui mediainfo libmediainfo
```
**FOR PACKAGING PDF FILES**
```
sudo yum install java-1.8.0-openjdk
wget http://downloads.verapdf.org/rel/verapdf-installer.zip
unzip verapdf-installer.zip
cd verapdf-greenfield-1.22.3/
./verapdf-install
Huom! PATH on oltava /usr/share/java/verapdf
```
**FOR USING FFMPEG PROGRAM COMMANDS**
https://computingforgeeks.com/install-use-ffmpeg-on-rocky-alma-9/
```
dnf install epel-release
dnf config-manager --set-enabled crb
dnf install --nogpgcheck https://mirrors.rpmfusion.org/free/el/rpmfusion-free-release-$(rpm -E %rhel).noarch.rpm -y
dnf install --nogpgcheck https://mirrors.rpmfusion.org/nonfree/el/rpmfusion-nonfree-release-$(rpm -E %rhel).noarch.rpm -y
dnf install ffmpeg ffmpeg-devel
```

