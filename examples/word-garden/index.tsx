import {configureDesign} from './src/ui';
configureDesign('word-garden');
import React from 'react';
import {AppRegistry} from 'react-native';
import {WordGarden} from './src/apps';
const Starter: React.ComponentType = WordGarden;
AppRegistry.registerComponent('com.vegabridge.samples.wordgarden.main', () => Starter);
