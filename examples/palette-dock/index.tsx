import {configureDesign} from './src/ui';
configureDesign('palette-dock');
import React from 'react';
import {AppRegistry} from 'react-native';
import {PaletteDock} from './src/apps';
const Starter: React.ComponentType = PaletteDock;
AppRegistry.registerComponent('com.vegabridge.samples.palettedock.main', () => Starter);
