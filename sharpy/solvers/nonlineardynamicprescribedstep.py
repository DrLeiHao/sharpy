"""
@modified   Alfonso del Carre
"""

import ctypes as ct
import numpy as np

import sharpy.structure.utils.xbeamlib as xbeamlib
from sharpy.utils.settings import str2bool
from sharpy.utils.solver_interface import solver, BaseSolver, solver_from_string
import sharpy.utils.settings as settings
import sharpy.utils.cout_utils as cout

_BaseStructural = solver_from_string('_BaseStructural')

@solver
class NonLinearDynamicPrescribedStep(_BaseStructural):
    """
    Structural solver used for the dynamic simulation of clamped structures or those subject to a prescribed motion.

    This solver provides an interface to the structural library (``xbeam``) and updates the structural parameters
    for every k-th step in the FSI iteration.

    This solver can be called as part of a standalone structural simulation or as the structural solver of a coupled
    aeroelastic simulation.

    """

    solver_id = 'NonLinearDynamicPrescribedStep'
    solver_classification = 'structural'

    settings_types = _BaseStructural.settings_types.copy()
    settings_default = _BaseStructural.settings_default.copy()
    settings_description = _BaseStructural.settings_description.copy()

    settings_table = settings.SettingsTable()
    __doc__ += settings_table.generate(settings_types, settings_default, settings_description)

    def __init__(self):
        self.data = None
        self.settings = None

    def initialise(self, data, custom_settings=None):
        self.data = data
        if custom_settings is None:
            self.settings = data.settings[self.solver_id]
        else:
            self.settings = custom_settings
        settings.to_custom_types(self.settings, self.settings_types, self.settings_default)

        # load info from dyn dictionary
        self.data.structure.add_unsteady_information(self.data.structure.dyn_dict, self.settings['num_steps'].value)


    def run(self, structural_step=None, dt=None):
        if dt is None:
            dt = self.settings['dt'].value
        if structural_step is None:
            structural_step = self.data.structure.timestep_info[-1]

        if self.data.ts > 0:
            try:
                structural_step.for_vel[:] = self.data.structure.dynamic_input[self.data.ts - 1]['for_vel']
                structural_step.for_acc[:] = self.data.structure.dynamic_input[self.data.ts - 1]['for_acc']
            except IndexError:
                pass

        xbeamlib.cbeam3_step_nlndyn(self.data.structure,
                                    self.settings,
                                    self.data.ts,
                                    structural_step,
                                    dt=dt)

        # self.extract_resultants(structural_step)
        self.data.structure.integrate_position(structural_step, dt)
        return self.data

    def add_step(self):
        self.data.structure.next_step()

    def next_step(self):
        pass
        # self.data.structure.next_step()
        # ts = len(self.data.structure.timestep_info) - 1
        # if ts > 0:
        #     self.data.structure.timestep_info[ts].for_vel[:] = self.data.structure.dynamic_input[ts - 1]['for_vel']
        #     self.data.structure.timestep_info[ts].for_acc[:] = self.data.structure.dynamic_input[ts - 1]['for_acc']
        #     self.data.structure.timestep_info[ts].unsteady_applied_forces[:] = self.data.structure.dynamic_input[ts - 1]['dynamic_forces']

    def extract_resultants(self, step=None):
        if step is None:
            step = self.data.structure.timestep_info[-1]
        applied_forces = self.data.structure.nodal_b_for_2_a_for(step.steady_applied_forces + step.unsteady_applied_forces,
                                                                 step)

        applied_forces_copy = applied_forces.copy()
        gravity_forces_copy = step.gravity_forces.copy()
        for i_node in range(self.data.structure.num_node):
            applied_forces_copy[i_node, 3:6] += np.cross(step.pos[i_node, :],
                                                         applied_forces_copy[i_node, 0:3])
            gravity_forces_copy[i_node, 3:6] += np.cross(step.pos[i_node, :],
                                                         gravity_forces_copy[i_node, 0:3])

        totals = np.sum(applied_forces_copy + gravity_forces_copy, axis=0)
        step.total_forces = np.sum(applied_forces_copy, axis=0)
        step.total_gravity_forces = np.sum(gravity_forces_copy, axis=0)
        return totals[0:3], totals[3:6]

    def update(self, tstep=None):
        self.create_q_vector(tstep)

    def create_q_vector(self, tstep=None):
        import sharpy.structure.utils.xbeamlib as xb
        if tstep is None:
            tstep = self.data.structure.timestep_info[-1]

        xb.xbeam_solv_disp2state(self.data.structure, tstep)
