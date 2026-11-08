import {configureDesign} from './src/ui';
configureDesign('room-rounds');
import React from 'react';
import {AppRegistry} from 'react-native';
import {RoomRounds} from './src/apps';
const Starter = RoomRounds;
AppRegistry.registerComponent('com.vegabridge.samples.roomrounds.main', () => Starter);
