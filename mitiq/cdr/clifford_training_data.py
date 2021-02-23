import cirq
from cirq.circuits import Circuit
from random import sample, choice, randint
import numpy as np
from mitiq._typing import QPROGRAM
from typing import List


# Global variable of Clifford angles in Rz gates:
CLIFFORD_ANGLES = (0.0, np.pi/2, np.pi, (3/2)*(np.pi))


def generate_training_circuits(
    circuit: Circuit,
    num_training_circuits: int,
    fraction_non_clifford: float,
    method_select: str = 'random',
    method_replace: str = 'nearest',
    **additional_options: dict
) -> (List[QPROGRAM], List[List[float]], List[List[float]]):
    """Function to return a list of near-Clifford circuits to create the
    training data.

    Args:
        circuit: A circuit of interest.
        num_training_circuits: Number of circuits in the returned training set,
                               assumes already compiled into gate set
                               (Rz, Rx, Z, X, CNOT)
        fraction_non_clifford: The (approximate) fraction of non-Clifford
                               gates in each returned circuit.
        method_select: option to define the way in which the non-Clifford
                              gates to replace with Cliffords are chosen can
                              take strings 'random' or 'probabilistic'.
        method_replace: str = option to define the way the chosen non-Clifford
                              gates are replace with a Clifford gate can take
                              strings 'random', 'probabilistic' or 'closest'.
        additional_options: dictionary with the following keys and values:
            'sigma_select': float -  postitive variable definined width of
                                     probability distribution used in choosing
                                     which non-Cliffords to replace, only has
                                     an impact if
                                     method_select = 'probabilistic'.
            'sigma_replace': float - positive variable definined width of
                                     probability distribution used in choosing
                                     which Clifford to replace the
                                     non-Clifford with, only has an impact if
                                     method_replace = 'probabilistic'.
    Returns:
        List[circ.Circuits]: list of near-Clifford circuits constructed from
                             the circuits of interest.
        List[List[float]]: list of list of angles that were replaced in each
                           training circuit.
        List[List[float]]: list of list of angles that were inserted in each
                           training circuit.
    """
    circuits_list = []
    # First turn circuit into an data array which is easier to deal with,
    # empty circuit is used to store qubit layout:
    data, empty_circuit = _circuit_to_array(circuit)
    mask_rz = data[1, :] == 'rz'
    rz_circ_data = data[:, mask_rz]
    mask_not_rz = data[1, :] != 'rz'
    not_rz_circ_data = data[:, mask_not_rz]
    mask_non_cliff = _is_clifford_angle(rz_circ_data[2, :])
    mask_non_cliff = ~mask_non_cliff
    rz_non_cliff = rz_circ_data[:, mask_non_cliff]
    mask_cliff = _is_clifford_angle(rz_circ_data[2, :])
    rz_cliff = rz_circ_data[:, mask_cliff]
    total_non_cliff = len(rz_non_cliff[0])

    # find all the non-Clifford gates:
    all_cliff = np.column_stack((not_rz_circ_data, rz_cliff))
    angles_original_list = []
    angles_replaced_list = []
    for n in range(num_training_circuits):
        # Convert data arry into cirq circuit and append it to the storage
        #  array:
        if additional_options:
            (projected_circuit, angles_original,
                angles_replaced) = _map_to_near_clifford(
                rz_non_cliff, all_cliff,
                empty_circuit,
                total_non_cliff,
                fraction_non_clifford,
                method_select,
                method_replace,
                additional_options=additional_options.get(
                    'additional_options'))
        else:
            (projected_circuit, angles_original,
                angles_replaced) = _map_to_near_clifford(rz_non_cliff,
                                                         all_cliff,
                                                         empty_circuit,
                                                         total_non_cliff,
                                                         fraction_non_clifford,
                                                         method_select,
                                                         method_replace)

        circuits_list.append(projected_circuit)
        # this information is to make sure the probabilistic methods are
        #  working as expected:
        angles_original_list.append(angles_original)
        angles_replaced_list.append(angles_replaced)
    return circuits_list, angles_original_list, angles_replaced_list


def _map_to_near_clifford(
    rz_non_cliff: np.ndarray,
    all_cliff: np.ndarray,
    empty_circuit: Circuit,
    total_non_cliff: int,
    fraction_non_clifford: float,
    method_select: str = 'random',
    method_replace: str = 'closest',
    **additional_options: dict
) -> (Circuit, List[float], List[float]):
    """ Function to take the information in some circuit of interest and
        return a near-Clifford circuit as constructed according to
        some user defined methods.
    Args:
        rz_non_cliff: array containing non-Clifford gates from the circuit of
                      interest.
        all_cliff: array containing Clifford gates from the circuit of
                   interest.
        empty_circuit: empty circuit strcuture (stores qubit geometry).
        total_non_cliff: total number of non-Clifford gates.
        fraction_non_clifford: the fraction of non-Clifford gates to replace
                               in the circuit of interest.
        method_select: string defining the method used to select the
                       non-Clifford gates to replace: 'random' or
                       'probabilistic'.
        method_replace: string defining method used to replace selected
                        non-Clifford gates: 'closest', 'random' or
                        'probabilistic'.
        sigma_select: width of probability distribution used in selection
                      of non-Clifford gates to replace, only has effect if
                      method_select = 'probabilistic'
        sigma_replace: width of probability distribution used in replacement
                       of selected non-Clifford gates, only has effect if
                       method_replace = 'probabilistic'.
        Returns:
            Circuit: Near-Clifford projected circuit.
            List[float]: list of angles replaced that were replaced in the
                         training circuit.
            List[float]: list of angles that were inserted in the training
                         circuit.
    """
    defult_sigma_select = 0.5
    defult_sigma_replace = 0.5
    N = int(fraction_non_clifford * total_non_cliff)
    empty_circuit_copy = empty_circuit.copy()
    rz_non_cliff_copy = rz_non_cliff.copy()
    additional_options = additional_options.get('additional_options')
    if additional_options:
        if 'sigma_select' in additional_options:
            sigma_select = additional_options.get('sigma_select')
            if 'sigma_replace' in additional_options:
                sigma_replace = additional_options.get('sigma_replace')
            else:
                sigma_replace = defult_sigma_replace
        elif 'sigma_select' not in additional_options:
            sigma_select = defult_sigma_select
            if 'sigma_replace' in additional_options:
                sigma_replace = additional_options.get('sigma_replace')
            else:
                raise Exception('additional options must be dicitonary with \
                                keys containing one or both of '
                                '"sigma_select" and "sigma_replace" both \
                                equal to some positive float')
    else:
        sigma_select = defult_sigma_select
        sigma_replace = defult_sigma_replace
    # Choose non Clifford gates to change according to selection methods:
    if method_select == 'random':
        columns_to_change = sample(
            np.arange(0, total_non_cliff, 1).tolist(), total_non_cliff-N)

    elif method_select == 'probabilistic':
        non_cliff_angles = rz_non_cliff_copy[2]
        # form a probability distribution:
        probabilities = _angle_to_probabilities(non_cliff_angles, sigma_select)
        prob_choose_gate = [k / sum(probabilities) for k in probabilities]
        columns_to_change = np.random.choice(
            np.arange(0, total_non_cliff, 1).tolist(),
            total_non_cliff - N, replace=False, p=prob_choose_gate)

    else:
        raise Exception('method_select must = "random", "probabilistic"')
    rz_non_cliff_selected = rz_non_cliff_copy[:, columns_to_change]
    # Remove these columns from the circuit data (as they are to be changed
    # below):
    rz_non_cliff_copy = np.delete(rz_non_cliff_copy, columns_to_change, axis=1)
    # Now the non Clifford gates have been selected, we need to decide which
    # Clifford gate to replace them with.
    # to store original angles replaced:
    angles_original = rz_non_cliff_selected[2, :].copy()
    if method_replace == 'closest':
        rz_non_cliff_selected[2, :] = _closest_clifford(
            rz_non_cliff_selected[2, :])

    elif method_replace == 'random':
        rz_non_cliff_selected[2, :] = _random_clifford(
            rz_non_cliff_selected[2, :])

    elif method_replace == 'probabilistic':
        rz_non_cliff_selected[2, :] = _probabilistic_angle_to_clifford(
            rz_non_cliff_selected[2, :], sigma_replace)

    else:
        raise Exception(
            'method_replace must = "closest", "random", "probabilistic"')
    # to store replaced angles:
    angles_replaced = rz_non_cliff_selected[2, :].copy()
    # Add back into rest of data and re-order instructions:
    new_circ = np.column_stack((all_cliff, rz_non_cliff_selected))
    new_circ = np.column_stack((new_circ, rz_non_cliff_copy))
    i = np.argsort(new_circ[0, :])
    projected_circuit_data = new_circ[:, i]
    projected_circuit = _array_to_circuit(
        projected_circuit_data, empty_circuit_copy)

    return projected_circuit, angles_original, angles_replaced


def count_non_cliffords(
    circuit: QPROGRAM,
) -> float:
    """Function to check how many non-Clifford gates are in a give circuit.

    Args:
        circuit: some quantum circuit already decomposed into the basis
                 {Rz, Rx(pi/2), CNOT, X}

    Returns:
        number of non-Clifford gates in the given circuit.
    """
    data, _ = _circuit_to_array(circuit)
    mask_rz = data[1, :] == 'rz'
    rz_circ_data = data[:, mask_rz]
    mask_non_cliff = _is_clifford_angle(rz_circ_data[2, :])
    mask_non_cliff = ~mask_non_cliff
    rz_non_cliff = rz_circ_data[:, mask_non_cliff]
    return len(rz_non_cliff[0])


def _circuit_to_array(
    circuit: QPROGRAM
) -> (np.ndarray, QPROGRAM):
    """Function to return the order of gates, their names and paramters in a
       more managable data structure than a Qiskit
    quantum circuit.

    Args:
        circ (QPROGRAM): cirq circuit (decomposed).

    Returns:
        data (np.ndarray): np.array([order], [names], [parameters], [qubits])
                           where order is the order of the gates from 0 to
                           depth, names are the names of the gates,
                           parameters are the paramters specifying the
                           gates and qubits and cbits are the qubits and
                           classical bits on which they act.
        QPROGRAM: empty circuit with same qubit layout as original.
    """
    order = []
    gates_list = []
    qubits_list = []
    operation_list = []
    parameters_list = []
    operations = circuit.all_operations()
    # loop through and construct arrays:
    for i, operation in enumerate(operations):
        operation_list.append(operation)
        order.append(i)
        qubits = operation.qubits
        gate = operation.gate
        if isinstance(gate, cirq.ops.common_gates.CXPowGate):
            qubit = [qubits[0], qubits[1]]
            parameters = None
            name = 'cx'
            gates_list.append(name)
            qubits_list.append(qubit)
            # cbit_list.append(None)
            parameters_list.append(parameters)
        elif isinstance(gate, cirq.ops.common_gates.ZPowGate):
            # print(gate.exponent())
            name = 'rz'
            parameters = float(gate.exponent)*np.pi
            gates_list.append(name)
            qubit = qubits[0]
            qubits_list.append(qubit)
            # cbit_list.append(None)
            parameters_list.append(float(parameters))
        elif isinstance(
                gate, cirq.ops.common_gates.XPowGate) and gate != cirq.X:
            name = 'rx'
            parameters = np.pi/2
            gates_list.append(name)
            qubit = qubits[0]
            qubits_list.append(qubit)
            # cbit_list.append(None)
            parameters_list.append(parameters)
        elif gate == cirq.X:
            parameters = None
            name = 'x'
            gates_list.append(name)
            qubit = qubits[0]
            qubits_list.append(qubit)
            # cbit_list.append(None)
            parameters_list.append(parameters)
        elif isinstance(gate, cirq.ops.MeasurementGate):
            parameters = None
            name = 'measure'
            gates_list.append(name)
            qubit = qubits[0]
            qubits_list.append(qubit)
            parameters_list.append(parameters)

    circuit_empty = circuit.copy()[0:0]
    data = np.array([order, gates_list,  parameters_list,
                     qubits_list, operation_list])

    return data, circuit_empty


def _array_to_circuit(
    data: np.ndarray,
    empty_circuit: QPROGRAM
) -> QPROGRAM:
    """ Function that takes the data array containing all the circuit data
        and turns it into a quantum circuit.

    Args:
        data: array containing circuit data np.array([order], [names],
              [parameters], [qubits], [operations]).
        empty_cricuit: cirq object containing circuit structure.
                       (empty circuit object)

    Returns:
        circ: QPROGRAM (cirq quantum circuit)

    """
    name_list = data[1]
    parameters_list = data[2]
    qubits_list = data[3]
    circuit = empty_circuit
    operation_list = data[4]
    # print(circuit)
    # print('new circuit')
    for i in range(len(name_list)):
        name = name_list[i]
        parameter = parameters_list[i]
        qubit = qubits_list[i]
        operation = operation_list[i]

        # print(operation)
        if name == 'rz':
            gate = cirq.ops.rz(parameter)
            circuit.append(gate(qubit))
        elif name == 'rx':
            gate = cirq.ops.rx(parameter)
            circuit.append(gate(qubit))
        elif name == 'cx':
            circuit.append(cirq.ops.CNOT(qubit[0], qubit[1]))
        elif name == 'x':
            circuit.append(cirq.X(qubit))
        elif name == 'measure':
            circuit.append([operation])
    return circuit


def _is_clifford_angle(
    ang: float,
    tol: float = 10 ** -5,
) -> bool:
    """Function to check if a given angle is Clifford.
    Args:
        ang: rotation angle in the Rz gate.
    Returns:
        bool: True / False for Clifford or not.
    """
    ang = ang % (2*np.pi)
    closest_clifford_angle = _closest_clifford(ang)
    if abs(closest_clifford_angle - ang) < tol:
        return True
    else:
        return False


# Vectorize function so it can take arrays of angles as its input.
_is_clifford_angle = np.vectorize(_is_clifford_angle)


def _closest_clifford(
    ang: float
) -> float:
    """Function to take angle and return the nearest Clifford angle note the
       usage of this function is vectorized so it takes and returns arrays.

    Args:
        ang: angle in Rz gate.

    Returns:
        Clifford angle: closest clifford angle.
    """
    ang = ang % (2*np.pi)
    ang_scaled = ang/(np.pi/2)
    # if just one min value, return the corresponding nearest cliff.
    if (abs((ang_scaled/0.5) - 1) > 10**(-6) and abs((
        ang_scaled/0.5) - 3) > 10**(-6) and (abs((ang_scaled/0.5) - 5)
                                             > 10**(-6))):
        index = int(np.round(ang_scaled)) % 4
        return CLIFFORD_ANGLES[index]
    # if two min values (ie two cliff gates equidistant) randomly choose the
    # cliff gate to return.
    else:
        index_list = [ang_scaled - 0.5, ang_scaled + 0.5]
        index = int(choice(index_list))
        return CLIFFORD_ANGLES[index]


# vectorize so function can take array of angles.
_closest_clifford = np.vectorize(_closest_clifford)


def _random_clifford(
    ang: float
) -> float:
    """Function to take angle and return the random Clifford angle note the
       usage of this function is vectorized so it takes and returns arrays.

    Args:
        ang: angle in Rz gate.

    Returns:
        Clifford angle: closest clifford angle.
    """
    random_index = randint(0, 3)
    clifford_angle = CLIFFORD_ANGLES[random_index]
    return clifford_angle


# vectorize so function can take array:
_random_clifford = np.vectorize(_random_clifford)


def _angle_to_probabilities(
    angle: float,
    sigma: float
) -> float:
    """Function to return probability disribtuion based on distance from
       angles to Clifford gates.

    Args:
        angle: angle to form probability distribution.
    Returns:
        discrete value of probability distribution calucalted from
        Prob_project = exp(-(dist/sigma)^2) where dist = sum(dists) is the
        sum of distances from each Clifford gate.
    """
    angle = angle % (2*np.pi)
    S = np.array([[1, 0.0], [0.0, 1j]])
    Rz = np.array([[1, 0.0], [0.0, np.exp(angle*1j)]])
    dists = []
    for i in range(4):
        if i == 0:
            i = 4
        diff = np.linalg.norm(Rz - S ** (i))
        dists.append(np.exp(-(diff / sigma) ** 2))
    return sum(dists)


# vectorize so function can take array of angles.
_angle_to_probabilities = np.vectorize(_angle_to_probabilities)


def _probabilistic_angle_to_clifford(
    ang: float,
    sigma: float,
) -> float:
    """Function to take angle and return the Clifford angle according to the
       probability distirbution:

                        prob = exp(-(dist/sigma)^2)

    where dist is the frobenius norm from the 4 clifford angles and the gate
    of interest. Note the usage of this function is vectorized so it takes
    and returns arrays.

    Args:
        ang: angle in Rz gate.
        sigma: width of probability distribution.

    Returns:
        Clifford angle: clifford angle to replace gate angle, calculated
        probabilistically.
    """
    ang = ang % (2*np.pi)
    S = np.array([[1, 0.0], [0.0, 1j]])
    Rz = np.array([[1, 0.0], [0.0, np.exp(ang*1j)]])
    dists = []
    for i in range(4):
        if i == 0:
            i = 4
        diff = np.linalg.norm(Rz - S ** (i))
        dists.append(np.exp(-(diff/sigma) ** 2))
    prob_gate = [i/sum(dists) for i in dists]
    cliff_ang = np.random.choice(
        CLIFFORD_ANGLES, 1, replace=False, p=prob_gate)
    return cliff_ang


# vectorize so function can take array of angles.
_probabilistic_angle_to_clifford = np.vectorize(
    _probabilistic_angle_to_clifford)
