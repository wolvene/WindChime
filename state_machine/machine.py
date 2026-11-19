from state_machine.states import (
    ProtocolState,
    SessionState,
    OperationState
)

from exceptions import ProtocolError


class StateMachine:
    """
    RogueSQL 协议状态机。

    负责管理协议接收状态、会话状态
    以及当前操作状态。
    """

    PROTOCOL_TRANSITIONS = {
        ProtocolState.LEN: {
            ProtocolState.DATA,
            ProtocolState.MORE_LENGTH,
            ProtocolState.CLOSED,
        },

        ProtocolState.MORE_LENGTH: {
            ProtocolState.DATA,
            ProtocolState.CLOSED,
        },

        ProtocolState.DATA: {
            ProtocolState.LEN,
            ProtocolState.CLOSED,
        },

        ProtocolState.CLOSED: set(),
    }

    SESSION_TRANSITIONS = {
        SessionState.INIT: {
            SessionState.AUTH,
            SessionState.CLOSED,
        },

        SessionState.AUTH: {
            SessionState.READY,
            SessionState.CLOSED,
        },

        SessionState.READY: {
            SessionState.CLOSED,
        },

        SessionState.CLOSED: set(),
    }

    OPERATION_TRANSITIONS = {
        OperationState.IDLE: {
            OperationState.PROCESSING,
        },

        OperationState.PROCESSING: {
            OperationState.COMPLETED,
            OperationState.FAILED,
        },

        OperationState.COMPLETED: {
            OperationState.IDLE,
        },

        OperationState.FAILED: {
            OperationState.IDLE,
        },
    }

    def __init__(self):

        self.protocol_state = ProtocolState.LEN

        self.session_state = SessionState.INIT

        self.operation_state = OperationState.IDLE

    @staticmethod
    def _transition(current, target, transitions, name):
        """
        执行通用状态转换。
        """

        if target == current:
            return

        allowed = transitions.get(current, set())

        if target not in allowed:
            raise ProtocolError(
                "Invalid {} transition: {} -> {}".format(
                    name,
                    current.name,
                    target.name
                )
            )

        return target

    def transition_protocol(self, target):
        result = self._transition(
            self.protocol_state,
            target,
            self.PROTOCOL_TRANSITIONS,
            "protocol"
        )

        if result is not None:
            self.protocol_state = result

    def transition_session(self, target):
        result = self._transition(
            self.session_state,
            target,
            self.SESSION_TRANSITIONS,
            "session"
        )

        if result is not None:
            self.session_state = result

    def transition_operation(self, target):
        result = self._transition(
            self.operation_state,
            target,
            self.OPERATION_TRANSITIONS,
            "operation"
        )

        if result is not None:
            self.operation_state = result

    def reset_protocol(self):
        """
        重置数据包接收状态。
        """

        if self.protocol_state == ProtocolState.CLOSED:
            raise ProtocolError(
                "Cannot reset a closed protocol state"
            )

        self.protocol_state = ProtocolState.LEN

    def reset_operation(self):
        """
        重置已完成或失败的操作。
        """

        if self.operation_state not in (
            OperationState.COMPLETED,
            OperationState.FAILED
        ):
            raise ProtocolError(
                "Current operation cannot be reset"
            )

        self.operation_state = OperationState.IDLE

    def close(self):
        """
        关闭当前会话。
        """

        self.protocol_state = ProtocolState.CLOSED

        self.session_state = SessionState.CLOSED

        self.operation_state = OperationState.IDLE

    @property
    def is_closed(self):
        return (
            self.protocol_state == ProtocolState.CLOSED
            or self.session_state == SessionState.CLOSED
        )

    def __repr__(self):

        return (
            "StateMachine("
            "protocol={}, "
            "session={}, "
            "operation={})"
        ).format(
            self.protocol_state.name,
            self.session_state.name,
            self.operation_state.name
        )
