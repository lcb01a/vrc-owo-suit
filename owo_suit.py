# pyright: reportMissingImports=false
from pythonosc import dispatcher
from event import Event
from config import Config
from gui import Gui
import params
import time
import clr
import os

dll_path = os.path.abspath(os.path.join(os.path.dirname(__file__), './owo/OWO.dll'))
from System.Reflection import Assembly
Assembly.UnsafeLoadFrom(dll_path)
from OWOGame import OWO, SensationsFactory, SensationWithMuscles, Muscle, ConnectionState

class OWOSuit:
    def __init__(self, config: Config, gui: Gui):
        self.config = config
        self.gui = gui
        self.active_muscles: set = set()
        self.osc_parameters: dict[str, Muscle] = {
            params.owo_suit_Pectoral_R: Muscle.Pectoral_R,
            params.owo_suit_Pectoral_L: Muscle.Pectoral_L,
            params.owo_suit_Abdominal_R: Muscle.Abdominal_R,
            params.owo_suit_Abdominal_L: Muscle.Abdominal_L,
            params.owo_suit_Arm_R: Muscle.Arm_R,
            params.owo_suit_Arm_L: Muscle.Arm_L,
            params.owo_suit_Dorsal_R: Muscle.Dorsal_R,
            params.owo_suit_Dorsal_L: Muscle.Dorsal_L,
            params.owo_suit_Lumbar_R: Muscle.Lumbar_R,
            params.owo_suit_Lumbar_L: Muscle.Lumbar_L,
        }
        self.distance_parameters: dict[str, tuple[float, float, float]] = {
            params.owo_suit_Abdominal_R_distance: (1, 0, 0),
            params.owo_suit_Abdominal_L_distance: (1, 0, 0),
            params.owo_suit_Dorsal_R_distance: (1, 0, 0),
            params.owo_suit_Dorsal_L_distance: (1, 0, 0),
        }
        self.impact_param = {
            params.owo_suit_Abdominal_R: params.owo_suit_Abdominal_R_distance,
            params.owo_suit_Abdominal_L: params.owo_suit_Abdominal_L_distance,
            params.owo_suit_Dorsal_R: params.owo_suit_Dorsal_R_distance,
            params.owo_suit_Dorsal_L: params.owo_suit_Dorsal_L_distance,
        }
        # start, duration, muscles
        self.active_hit: None | tuple[float, float, list[Muscle]] = None
        self.queued_sensation: None | SensationWithMuscles = None
        self.muscles_to_parameters: dict[Muscle, str] = {
            value: key for key, value in self.osc_parameters.items()}
        self.has_connected_already = False
        self.is_connecting = False
        self.is_paused = False
        self.on_connection_state_change = Event()

    def toggle_interactions(self):
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.gui.print_terminal(
                "Interactions Paused.")
        else:
            self.gui.print_terminal(
                "Interactions Continued.")

    def setup_muscle(self, muscle: Muscle, parameter: str) -> Muscle:
        intensities = self.config.get_by_key("intensities")
        intensity = intensities.get(parameter)
        return muscle.WithIntensity(intensity)

    def watch(self) -> None:
        while True:
            try:
                if self.has_connected_already:
                    self.gui.handle_active_muscle_reset()

                    # if self.queued_sensation:
                    #     OWO.Send(self.queued_sensation)
                    #     self.queued_sensation = None
                    #     time.sleep(.05)
                    #     continue

                    if self.active_hit:
                        if ((self.active_hit[0] + self.active_hit[1]) < time.time()):
                            self.active_hit = None
                        else:
                            time.sleep(.05)
                            continue

                    if len(self.active_muscles) > 0 and not self.is_paused:
                        muscles = []
                        frequency = self.config.get_by_key("frequency") or 50
                        sensation = SensationsFactory.Create(
                            frequency,
                            0.1, # durationSeconds
                            100, # intensityPercentage
                            0,   # rampUpMillis
                            0,   # rampDownMillis
                            0    # exitDelaySeconds
                        )
                        for muscle in self.active_muscles:
                            parameter = self.muscles_to_parameters.get(muscle)
                            self.gui.handle_active_muscle_update(
                                parameter=parameter)
                            muscles.append(self.setup_muscle(muscle, parameter))
                        sensation = SensationWithMuscles(sensation, muscles)
                        if len(muscles) > 0:
                            OWO.Send(sensation)

            except RuntimeError:  # race condition for set changing during iteration
                pass
            time.sleep(.05)

    def on_collission_enter(self, address: str, *args) -> None:
        if address in self.osc_parameters:
            if len(args) != 1:
                return
            was_entered: bool = args[0]
            if type(was_entered) != bool:
                return
            muscle = self.osc_parameters.get(address)
            if was_entered:
                self.active_muscles.add(muscle)
                if address in self.impact_param:
                    speed = self.distance_parameters[self.impact_param[address]][2]
                    max_intensity = 100
                    min_intensity = 10
                    min_speed = 0
                    max_speed = 10

                    intensity = int((speed-min_speed)*(min_intensity-max_intensity)/(min_speed-max_speed) + min_intensity)

                    if intensity < 20:
                        return

                    if not self.active_hit:
                        sensation = SensationsFactory.Create(80, 1, intensity, 0, 10, 0)
                        self.active_hit = (time.time(), 1.0, [muscle])
                        # self.queued_sensation = SensationWithMuscles(sensation, [muscle])
                        OWO.Send(SensationWithMuscles(sensation, [muscle]))
                    else:
                        start, duration, muscles = self.active_hit
                        if (start+duration/2.0) < time.time():
                            return
                        muscles.append(muscle)
                        self.active_hit = (start, duration, muscles)
                        sensation = SensationsFactory.Create(80, 1, intensity, 0, 10, 0)
                        sensation = SensationWithMuscles(sensation, muscles)
                        # self.queued_sensation = sensation
                        OWO.Send(sensation)

            else:
                self.active_muscles.discard(muscle)
        if address in self.distance_parameters:
            if len(args) != 1:
                return
            last, ts, speed = self.distance_parameters[address]
            current = args[0]
            distance = current - last
            now = time.time()
            if ts == now:
                return
            current_speed = abs(distance/(now - ts))
            val = (current, now, current_speed)
            self.distance_parameters[address] = val


    def map_parameters(self, dispatcher: dispatcher.Dispatcher) -> None:
        dispatcher.set_default_handler(self.on_collission_enter)

    def connect(self) -> bool:
        owo_ip = self.config.get_by_key("owo_ip")
        if type(owo_ip) is str and owo_ip != "":
            OWO.Connect(owo_ip)
            if self.is_connected():
                return True
        OWO.AutoConnect()
        return self.is_connected()

    def is_connected(self) -> bool:
        return OWO.ConnectionState == ConnectionState.Connected

    def dispatch_connection_state_change(self) -> None:
        if self.is_connecting:
            self.on_connection_state_change.dispatch('CONNECTING')
            return
        if self.is_connected():
            self.on_connection_state_change.dispatch('CONNECTED')
            return
        self.on_connection_state_change.dispatch('DISCONNECTED')

    def retry_connect(self, *args) -> None:
        if self.is_connecting:
            return
        self.gui.print_terminal("Connecting to suit...")
        self.is_connecting = True
        self.dispatch_connection_state_change()
        ok = self.connect()
        while not ok:
            ok = self.connect()
            time.sleep(1)
        self.is_connecting = False
        if self.is_connected():
            self.gui.print_terminal("Connection complete!")
        self.has_connected_already = True
        self.dispatch_connection_state_change()

    def init(self) -> None:
        self.gui.on_connect_clicked.add_listener(self.retry_connect)
        self.gui.on_toggle_interaction_clicked.add_listener(
            self.toggle_interactions)
        self.on_connection_state_change.add_listener(
            self.gui.handle_connecting_state_change)
