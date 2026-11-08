import {configureDesign} from './src/ui';
configureDesign('story-sparks');
import React from 'react';
import {AppRegistry} from 'react-native';
import {StorySparks} from './src/apps';
const Starter = StorySparks;
AppRegistry.registerComponent('com.vegabridge.samples.storysparks.main', () => Starter);
