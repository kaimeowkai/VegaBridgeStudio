import {configureDesign} from './src/ui';
configureDesign('focus-harbor');
import React from 'react';
import {AppRegistry} from 'react-native';
import {FocusHarbor} from './src/apps';
const Starter: React.ComponentType = FocusHarbor;
AppRegistry.registerComponent('com.brutalgamestudios.focusharbortv.main', () => Starter);
