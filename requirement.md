Project Assignment 3: Making Your Systems Fault Tolerant via 2PC & Raft

## 1. Introduction
The goal of this project is to provide you with hands-on experience in implementing a simplified version of consensus algorithms, 2PC (two phase commit protocol) and Raft. Through this assignment, you will understand how 2PC achieves distributed commit and Raft achieves fault-tolerant consensus, handle leader election, maintain log consistency, and manage distributed state transitions.

You can use any programming language(s) to implement this project. 

You should use gRPC for communication between nodes/processes and Docker for containerization.

You should read Section 2 (Consensus Algorithms), Section 3 (2PC), and Section 4 (Raft), before you start the implementation of the assignment detailed in Section 5 (Assignment).

The estimated workload for this project is about 3 weeks. Please start working on it as soon as possible.

## 2. Why are Consensus Algorithms Needed? [1]
In distributed systems, if we want to replicate changes on different processes, we just need to send them in order. However, a main problem with this simple approach is that we may fail to send changes to peers for many reasons, e.g., process crash, network failure. If we wait for all replication to be ready, we will lose availability. To achieve high availability, we can't wait for all processes to apply changes to make progress, but we need a mechanism to ensure that all processes apply changes in the same order. That's where consensus algorithm comes in.

## 3. 2PC
### 3.1 Overview
2PC is a specialized type of consensus protocol. It coordinates all the processes that participate in a distributed atomic transactionLinks to an external site. on whether to commit or abort (roll back) the transaction [2]. It originates from a simple idea. For example, you want to arrange a game with three friends on some day, what would you do? First, you need to propose a time and ask each of your picked friends to see if they are available on that time. If all of them reply you with a yes, then you need to tell your friends to settle on that time. Otherwise, if any of them is not free on that moment, you need to tell your friends to cancel that meeting. [1]

### 3.2 Details [3]
2PC designate one node as a coordinator and the rest of the nodes as participants. It consists of two phases, a voting phase and a decision phase. 

During the voting phase,

- The coordinator sends a vote-request message to all participants.
- When a participant receives a vote-request message, it returns either a vote-commit message to the coordinator, telling the coordinator that it is prepared to locally commit its part of the transaction, or otherwise, a vote-abort message.

Following the voting phase is the decision phase.

- The coordinator collects all votes from the participants. If all participants have voted to commit the transaction, then so will the coordinator. In that case, it sends a global-commit message to all participants. However, if one participant had voted to abort the transaction, the coordinator will also decide to abort the transaction and multicasts a global-abort message.
- Each participant that voted for a commit waits for the final reaction by the coordinator. If a participant receives a global-commit message, it locally commits the transaction. Otherwise, when receiving a global-abort message, the transaction is locally aborted as well.

## 4. Raft

### 4.1 Overview
Raft allows the members of a distributed system to agree on a sequence of values even in the presence of failures. It achieves consensus via an elected leader. A server in a raft cluster is either a leader or a follower, and can be a candidate in the precise case of an election (leader unavailable). The leader is responsible for log replication to the followers. It regularly informs the followers of its existence by sending a heartbeat message. Each follower has a timeout (typically between 150 and 300 ms) in which it expects the heartbeat from the leader. The timeout is reset on receiving the heartbeat. If no heartbeat is received the follower changes its status to candidate and starts a leader election.

### 4.2 Details [4]
Raft achieves consensus through two relatively independent subproblems: leader election and log replication.

#### 4.2.1 Leader Election
When the existing leader fails or when the algorithm initializes, a new leader needs to be elected.

In this case, a new term starts. A term is an arbitrary period of time on the server for which a new leader should be elected. Each term starts with a leader election. If the election is completed successfully (i.e. a single leader is elected) the term keeps going with normal operations orchestrated by the new leader. If the election is a failure, a new term starts, with a new election.

A leader election is started by a candidate server. A server becomes a candidate if it receives no communication by the leader over a period called the election timeout, so it assumes there is no acting leader anymore. 

The candidate server starts the election by increasing the term counter, voting for itself as new leader, and sending a message to all other servers requesting their vote. A server will vote only once per term, on a first-come-first-served basis. If a candidate receives a message from another server with a term number larger than the candidate's current term, then the candidate's election is defeated and the candidate changes into a follower and recognizes the leader as legitimate. If a candidate receives a majority of votes, then it becomes the new leader. If neither happens, e.g., because of a split vote, then a new term starts, and a new election begins.

Raft uses a randomized election timeout to ensure that split vote problems are resolved quickly. This should reduce the chance of a split vote because servers won't become candidates at the same time. This means only a single server will time out, win the election, then become leader and send heartbeat messages to other servers before any of the followers can become candidates.

#### 4.2.2 Log Replication
The leader is responsible for the log replication. The leader accepts client requests.

Each client request consists of a command to be executed in the cluster. After being appended to the leader's log as a new entry, each of the requests is forwarded to the followers as AppendEntries messages. 

Once the leader receives confirmation from half or more of its followers that the entry has been successfully replicated, the leader executes the request and the request is considered committed.

Once a follower learns that a log entry is committed, it also executes/commits the corresponding request. This ensures consistency of the logs between all the servers through the cluster.

In the case of a leader crash, the logs can be left inconsistent, with some logs from the old leader not being fully replicated through the cluster. The new leader will then handle inconsistency by forcing the followers to duplicate its own log. To do so, for each of its followers, the leader will compare its log with the log from the follower, find the last entry where they agree, then delete all the entries coming after this critical entry in the follower log and replace it with its own log entries. This mechanism will restore log consistency in a cluster subject to failures.

## 5. Assignment 
### Q0. Bidding on Three Different Distributed Systems
To encourage cross-group collaboration, each group needs to select three implementations (developed by other groups for project assignment 2) to extend for this project. 

A list of all available implementations can be accessed here (https://docs.google.com/spreadsheets/d/1ebTJvuLDw2fnFPJ7Y1yPU7Qs4uLaGxj8lOD58UoQjL4/edit?usp=sharingLinks to an external site.). Please carefully review all options to identify the ones that align with your interests and technical strengths. 

Each group must select three distinct implementations that were proposed by other groups in the shared google sheet above.

Each implementation can be selected by up to three groups (or another cap defined by the instructor). Once the limit is reached, later bids for that implementation will not be accepted. Groups cannot select their own implementation.

### Q1. [Workload: ~0.5 week]
Implement the voting phase of 2PC on one of the three selected implementations. You can just implement 2PC to support a single functionality. 

You should define your own gRPC data structure and service methods (RPCs) in a proto file. 

You should implement the following steps for the vote phase.

The coordinator sends a vote-request message to all participants.
When a participant receives a vote-request message, it returns either a vote-commit message to the coordinator, telling the coordinator that it is prepared to locally commit its part of the transaction, or otherwise, a vote-abort message.
Finally, you should containerize your implementation for each node and ensure different containerized nodes (at least 5 nodes) can communicate with each other.

### Q2. [Workload: ~0.5 week]
Implement the decision phase of 2PC on the same selected implementation in Q1. 

You should define your own gRPC data structure and service methods (RPCs) in the same proto file that you have created in Q1. 

You should implement the following steps for the decision phase.

The coordinator collects all votes from the participants. If all participants have voted to commit the transaction, then so will the coordinator. In that case, it sends a global-commit message to all participants. However, if one participant had voted to abort the transaction, the coordinator will also decide to abort the transaction and multicasts a global-abort message.
Each participant that voted for a commit waits for the final reaction by the coordinator. If a participant receives a global-commit message, it locally commits the transaction. Otherwise, when receiving a global-abort message, the transaction is locally aborted as well.
To allow the voting phase and the decision phase implemented in different languages to operate on the same node, you should use gRPC for the communication between these two phases within the same node (container). You should define needed gRPC data structure and service methods (RPCs) in the same proto file. 

For each RPC method being called, you should print a message on the client side in the format of Phase <phase_name> of Node <node_id> sends RPC <rpc_name> to Phase <phase_name> of Node <node_id>. On the server side, you should also print a message in the format of Phase <phase_name> of Node <node_id> sends RPC <rpc_name> to Phase <phase_name> of Node <node_id. Note that you need to print these messages for both voting and decision phases. 

Finally, you should containerize your implementation for each node and ensure different containerized nodes (at least 5 nodes) can communicate with each other.

### Q3. [Workload: ~0.5 week]
Implement the leader election of a simplified version of Raft on one of the three selected implementations. 

You should define the needed gRPC data structure and service methods (RPCs) in a new proto file. 

You should implement the two timeout settings in Raft: heartbeat timeout and election timeout. Heartbeat timeout should be set at 1 second for all the processes. The election timeout should be chosen randomly from a fixed interval, [1.5 seconds, 3 seconds], for each single process/node. 

At the start of your program, all processes/nodes should begin in the follower state. If a follower does not receive a heartbeat from a leader within its randomized election timeout, it assumes that no leader currently exists and transitions to the candidate state.

As a candidate, the process increments its term, votes for itself, and sends RequestVote RPCs to the other processes in the cluster. If it receives a majority of votes, it becomes the leader and begins sending periodic AppendEntries RPCs to all the other processes as heartbeat. If another candidate wins the election first or the node fails to gather a majority, it reverts to the follower state and waits for further heartbeats.

For each RPC method being called, you should print a message on the client side in the format of Node <node_id> sends RPC <rpc_name> to Node <node_id>. On the server side, you should also print a message in the format of Node <node_id> runs RPC <rpc_name> called by Node <node_id>.

Finally, you should containerize your implementation for each node and ensure different containerized nodes (at least 5 nodes) can communicate with each other.

### Q4. [Workload: ~0.5 week]
Implement the log replication of a simplified version of Raft on top of the same selected implementation in Q3. 

You should define the needed gRPC data structure and service methods (RPCs) in the same proto file that you have created in Q3. You should implement the following actions:

Each process/node should maintain a log of operations. Log contains operations: (1) have already been committed; (2) are pending.

For each client's request for executing operation o,

- The current leader (1) receives request, (2) append <o, t, k+1> to log and (3) sends its entire log to all the other servers, along with current value of c (c is the index of the most recently committed operation) on next heartbeat.
- Each follower copies the entire log and returns ACK to leader. Each follower should check and execute operations to make sure all operations up to and including index c have already been executed.
- When leader receives a majority of ACKs, leader executes all the pending executions, returns the results to the client, and increments c.
For each RPC method being called, you should print a message on the client side in the format of Node <node_id> sends RPC <rpc_name> to Node <node_id>. On the server side, you should also print a message in the format of Node <node_id> runs RPC <rpc_name> called by Node <node_id>.

Note that since a client can connect to any one of the processes (not necessarily the leader) and send its request, you should implement that the receiver forwards the request to the leader.

Finally, you should containerize your implementation for each node and ensure different containerized nodes (at least 5 nodes) can communicate with each other.

### Q5. [Workload: ~0.5 Week]
You should design and implement 5 different test cases (related to failures) for your Raft implementation. For example, a new node entering the system (no matter which node you implement) should be considered as one test case. 

You should document them and include the captured screenshots of their executions in the final report.

## 4. Turning in Your Solution
You should make sure that your deliverables include source code of your 2PC and Raft implementation, a README file, and a report. You should put all the required files into a zipped folder and upload it to Canvas.

In the README file (5 pts), you should include explains:

- How to compile and run your program;
- Anything unusual about your solution that the TA should know;
- Any external sources referenced while working on your solution.
Remember to include your Github link in your README and report.

In the report, you should make sure you clearly list your names and student IDs. You should clearly mention which student worked on which part of the project. 

NOTE: The late penalty is 20 points per day.

## References:
[1] https://renjieliu.gitbooks.io/consensus-algorithms-from-2pc-to-raft/content/index.htmlLinks to an external site. 

[2] https://en.wikipedia.org/wiki/Two-phase_commit_protocolLinks to an external site. 

[3] Andrew S. Tanenbaum and Maarten Van Steen, Distributed Systems: Principles and Paradigms (4th Edition)

[4] https://en.wikipedia.org/wiki/Raft_(algorithm)Links to an external site. 