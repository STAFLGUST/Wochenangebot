// Metro: zusätzlich den gemeinsamen Angebotskern der Website (app/assets/offer-core.js) einbinden,
// damit Merklisten-Schlüssel und Aufbereitung in App und Website identisch sind.
const path = require('path');
const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);
config.watchFolders = [...(config.watchFolders || []), path.resolve(__dirname, '../app/assets')];
module.exports = config;
