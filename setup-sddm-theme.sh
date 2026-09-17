#!/usr/bin/env bash
set -e

# Configurar fondo en el tema breeze
mkdir -p /usr/share/sddm/themes/breeze
cat << 'EOF' > /usr/share/sddm/themes/breeze/theme.conf.user
[General]
background=/usr/share/sddm/waywallen_lock.jpg
EOF

# Configurar fondo en WinSur-dark si existe
if [[ -d /usr/share/sddm/themes/WinSur-dark ]]; then
cat << 'EOF' > /usr/share/sddm/themes/WinSur-dark/theme.conf.user
[General]
background=/usr/share/sddm/waywallen_lock.jpg
EOF
fi

# Corregir la línea de tema en kde_settings.conf si tiene la errata
if [[ -f /etc/sddm.conf.d/kde_settings.conf ]]; then
    sed -i 's/^Curent=.*/Current=breeze/' /etc/sddm.conf.d/kde_settings.conf
    sed -i 's/^Current=breezeinSur-dark/Current=breeze/' /etc/sddm.conf.d/kde_settings.conf
fi

# Asegurar permisos del archivo de imagen
touch /usr/share/sddm/waywallen_lock.jpg
chown rodrigo:rodrigo /usr/share/sddm/waywallen_lock.jpg
chmod 644 /usr/share/sddm/waywallen_lock.jpg

echo "SDDM configurado correctamente con el fondo de Waywallen."
